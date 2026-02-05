import os
import re
import json
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from pypdf import PdfReader
from docx import Document
import speech_recognition as sr

# Support for MoviePy versions with better compatibility
try:
    from moviepy import VideoFileClip
    MOVIEPY_AVAILABLE = True
except ImportError:
    try:
        from moviepy.editor import VideoFileClip
        MOVIEPY_AVAILABLE = True
    except ImportError:
        MOVIEPY_AVAILABLE = False
        VideoFileClip = None

app = Flask(__name__)
UPLOAD_FOLDER = 'documents'
CACHE_FILE = 'document_cache.json'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Document cache to avoid re-processing
document_cache = {}

def extract_text(filepath):
    """Robust text extraction for multiple formats."""
    filename = os.path.basename(filepath)
    
    # Check cache first
    if filename in document_cache:
        return document_cache[filename]
    
    ext = os.path.splitext(filepath)[1].lower()
    text = ""
    
    try:
        if ext == '.txt':
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
        elif ext == '.pdf':
            reader = PdfReader(filepath)
            for page in reader.pages:
                content = page.extract_text()
                if content:
                    text += content + "\n"
        elif ext == '.docx' or ext == '.doc':
            doc = Document(filepath)
            text = "\n".join([para.text for para in doc.paragraphs])
        elif ext in ['.mp4', '.mkv', '.mov', '.avi', '.flv', '.webm']:
            text = extract_video_audio_to_text(filepath)
        else:
            print(f"Unsupported file format: {ext}")
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        text = f"[Error processing {filename}: {str(e)[:50]}]"
    
    # Cache the result
    document_cache[filename] = text
    return text

def extract_video_audio_to_text(filepath):
    """Extracts audio from video and converts to text."""
    if not MOVIEPY_AVAILABLE:
        return "[Video processing unavailable - moviepy not installed]"
    
    temp_audio = "temp_audio.wav"
    try:
        print(f"Processing video: {filepath}")
        
        # Load video with error handling
        try:
            video = VideoFileClip(filepath)
        except Exception as e:
            print(f"Error loading video: {e}")
            return f"[Error loading video: {str(e)[:50]}]"
        
        if video.audio is None:
            video.close()
            return "[Video has no audio track]"
        
        try:
            # Try different parameter combinations for compatibility
            try:
                # Newer moviepy versions
                video.audio.write_audiofile(temp_audio, codec='pcm_s16le', verbose=False, logger=None)
            except TypeError:
                # Older moviepy versions
                try:
                    video.audio.write_audiofile(temp_audio, codec='pcm_s16le', verbose=False)
                except TypeError:
                    # Even older versions
                    video.audio.write_audiofile(temp_audio, codec='pcm_s16le')
            
            video.close()
        except Exception as e:
            print(f"Error extracting audio: {e}")
            video.close()
            return f"[Error extracting audio: {str(e)[:50]}]"
        
        # Transcribe audio
        recognizer = sr.Recognizer()
        try:
            with sr.AudioFile(temp_audio) as source:
                print(f"Transcribing audio from {temp_audio}...")
                audio_data = recognizer.record(source)
                try:
                    text = recognizer.recognize_google(audio_data)
                    print(f"Successfully transcribed {len(text)} characters")
                    return text
                except sr.UnknownValueError:
                    return "[Video audio could not be understood]"
                except sr.RequestError as e:
                    return f"[Speech recognition error: {str(e)[:50]}]"
        except Exception as e:
            print(f"Error transcribing audio: {e}")
            return f"[Error transcribing: {str(e)[:50]}]"
            
    except Exception as e:
        print(f"Error processing video: {e}")
        return f"[Video processing error: {str(e)[:50]}]"
    finally:
        # Clean up temp file
        if os.path.exists(temp_audio):
            try:
                os.remove(temp_audio)
            except:
                pass

def normalize_text(text):
    """Normalize text for comparison."""
    text = text.lower()
    text = re.sub(r'[^\w\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def extract_keywords(question):
    """Extract important keywords from question with scoring."""
    stop_words = {
        'what', 'is', 'how', 'why', 'when', 'where', 'which', 'who', 'the', 'a', 'an',
        'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'from',
        'can', 'could', 'would', 'should', 'do', 'does', 'did', 'am', 'is', 'are', 'be',
        'been', 'being', 'have', 'has', 'had', 'this', 'that', 'these', 'those',
        'please', 'tell', 'me', 'about', 'explain', 'describe', 'give', 'show', 'find',
        'information', 'document', 'file', 'know', 'need', 'want'
    }
    
    words = normalize_text(question).split()
    
    # Score keywords by importance
    keywords = []
    for w in words:
        if w not in stop_words and len(w) > 2:
            score = len(w) # Longer words are more specific
            if w.endswith(('ing', 'ed', 'ly')):
                score += 1
            keywords.append({'word': w, 'score': score})
    
    # Sort by score and take top 5
    keywords.sort(key=lambda x: x['score'], reverse=True)
    return [k['word'] for k in keywords[:5]]

def calculate_relevance_score(text, question, keywords):
    """Calculate relevance score using advanced keyword matching."""
    if not keywords:
        return 0
    
    norm_text = normalize_text(text)
    norm_question = normalize_text(question)
    text_words = norm_text.split()
    
    if len(text_words) < 3:
        return 0
    
    score = 0
    keyword_found_count = 0
    
    # Check for each keyword
    for keyword in keywords:
        # Exact word match
        exact_matches = text_words.count(keyword)
        if exact_matches > 0:
            score += exact_matches * 10
            keyword_found_count += 1
        else:
            # Partial match
            partial_matches = sum(1 for w in text_words if keyword in w)
            if partial_matches > 0:
                score += partial_matches * 3
                keyword_found_count += 1
    
    # Bonus for multiple keywords in proximity
    if keyword_found_count >= 2:
        for i, word in enumerate(text_words):
            window = text_words[i:i+8]
            keyword_in_window = sum(1 for kw in keywords if any(kw in w for w in window))
            if keyword_in_window >= 2:
                score += 15
                break
    
    # Bonus for question phrases
    question_words = norm_question.split()
    for i in range(len(question_words) - 1):
        phrase = f"{question_words[i]} {question_words[i+1]}"
        if phrase in norm_text:
            score += 12
    
    # Penalty for very long texts with poor matches
    text_length = len(text_words)
    if score < 15 and text_length > 200:
        score = max(0, score - (text_length / 50))
    
    # Normalize by length
    if text_length > 0:
        length_factor = min(1.0, 80 / text_length)
        score = score * length_factor
    
    return score

def find_best_context(text, question, keywords):
    """Find the most relevant 3-4 sentence context around keywords."""
    # Split by sentences
    sentences = re.split(r'(?<=[.!?])\s+', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 10]
    
    if not sentences:
        return text[:300] if len(text) > 300 else text
    
    best_sentence_index = -1
    best_score = 0
    
    # Find sentence with highest keyword density
    for i, sentence in enumerate(sentences):
        norm_sentence = normalize_text(sentence)
        sentence_words = norm_sentence.split()
        
        if len(sentence_words) < 4:
            continue
            
        keyword_score = 0
        for keyword in keywords:
            if keyword in norm_sentence:
                keyword_score += 8
        
        if keyword_score > best_score:
            best_score = keyword_score
            best_sentence_index = i
    
    # If no good sentence found, check for any keyword match
    if best_sentence_index == -1:
        for i, sentence in enumerate(sentences):
            norm_sentence = normalize_text(sentence)
            for keyword in keywords:
                if keyword in norm_sentence:
                    best_sentence_index = i
                    break
            if best_sentence_index != -1:
                break
    
    # Still no match, return beginning
    if best_sentence_index == -1:
        context = " ".join(sentences[:3])
        return context[:400] + "..." if len(context) > 400 else context
    
    # Get context around best sentence
    start = max(0, best_sentence_index - 2)
    end = min(len(sentences), best_sentence_index + 3)
    context = " ".join(sentences[start:end])
    
    # Trim if too long
    if len(context) > 500:
        # Try to cut at sentence boundary
        shortened = context[:500]
        last_period = shortened.rfind('. ')
        if last_period > 250:
            context = shortened[:last_period + 1]
        else:
            context = shortened + "..."
    
    return context

def get_best_answer(question, documents_with_source):
    """Advanced answer extraction with smart context finding."""
    if not documents_with_source:
        return {
            'answer': 'No documents found in the /documents folder.',
            'source': 'System',
            'confidence': 0,
            'source_file': 'None',
            'match_type': 'no_documents'
        }
    
    keywords = extract_keywords(question)
    print(f"Searching for: '{question}'")
    print(f"Keywords extracted: {keywords}")
    
    if not keywords:
        return {
            'answer': 'Please ask a more specific question with clear keywords.',
            'source': 'System',
            'confidence': 0,
            'source_file': 'None',
            'match_type': 'no_keywords'
        }
    
    scored_results = []
    
    # Search each document
    for filename, content in documents_with_source.items():
        if not content or len(content.strip()) < 20:
            continue
        
        # Skip error messages and video processing errors
        if (content.startswith('[Error') or content.startswith('[Video') or 
            content.startswith('[Unable') or content.startswith('[Video processing')):
            continue
        
        # Score the entire document
        doc_score = calculate_relevance_score(content, question, keywords)
        
        if doc_score > 0.5: # Some relevance found
            # Find best context
            best_context = find_best_context(content, question, keywords)
            
            # Score the context specifically
            context_score = calculate_relevance_score(best_context, question, keywords)
            
            if context_score > 1: # Minimum threshold
                scored_results.append({
                    'context': best_context,
                    'score': context_score,
                    'source_file': filename,
                    'full_score': doc_score,
                    'text_length': len(content)
                })
    
    if not scored_results:
        return {
            'answer': f'No specific information found about "{question}". Try using different keywords.',
            'source': 'System',
            'confidence': 0,
            'source_file': 'None',
            'match_type': 'no_match'
        }
    
    # Sort by score
    scored_results.sort(key=lambda x: x['score'], reverse=True)
    
    # Get top 3 results for debugging
    top_results = scored_results[:3]
    print(f"Top {len(top_results)} results:")
    for i, result in enumerate(top_results):
        print(f" {i+1}. {result['source_file']} (score: {result['score']:.2f})")
    
    best_result = scored_results[0]
    best_answer = best_result['context']
    best_score = best_result['score']
    source_file = best_result['source_file']
    
    # Calculate confidence
    base_confidence = min(100, int(best_score * 4))
    
    # Boost confidence for exact matches
    norm_answer = normalize_text(best_answer)
    exact_keyword_matches = sum(1 for kw in keywords if kw in norm_answer)
    if exact_keyword_matches >= 2:
        base_confidence = min(100, base_confidence + 15)
    
    # Determine match type
    if best_score > 25:
        match_type = 'excellent'
    elif best_score > 15:
        match_type = 'good'
    elif best_score > 8:
        match_type = 'fair'
    else:
        match_type = 'weak'
    
    return {
        'answer': best_answer,
        'source': 'Document Analysis',
        'confidence': base_confidence,
        'source_file': source_file,
        'keywords_found': keywords,
        'match_type': match_type,
        'score': best_score
    }

def load_documents():
    """Load and cache all documents."""
    documents_with_source = {}
    doc_summary = []
    
    files = os.listdir(UPLOAD_FOLDER)
    print(f"Found {len(files)} files in documents folder")
    
    for filename in files:
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        if os.path.isfile(filepath):
            print(f" Loading: {filename}")
            content = extract_text(filepath)
            
            # Clean up content
            if content and not content.startswith('[Error') and len(content.strip()) > 10:
                documents_with_source[filename] = content
                
                word_count = len(content.split())
                doc_summary.append({
                    'name': filename,
                    'size': len(content),
                    'word_count': word_count,
                    'timestamp': datetime.now().isoformat()
                })
            else:
                print(f" Skipped - empty or error")
    
    print(f"Successfully loaded {len(documents_with_source)} documents")
    return documents_with_source, doc_summary

@app.route('/')
def index():
    """Serve the main chatbot interface."""
    return render_template('index.html')

@app.route('/ask', methods=['POST'])
def ask():
    """Process user question and return answer."""
    try:
        user_query = request.json.get('question', '').strip()
        
        if not user_query:
            return jsonify({
                'answer': 'Please enter a question.',
                'source': 'System',
                'confidence': 0,
                'source_file': 'None',
                'match_type': 'empty_query'
            })
        
        # Load documents
        documents_with_source, doc_summary = load_documents()
        
        if not documents_with_source:
            return jsonify({
                'answer': 'No documents found. Please add files to the documents folder.',
                'source': 'System',
                'confidence': 0,
                'source_file': 'None',
                'match_type': 'no_documents',
                'documents': []
            })
        
        # Get best answer
        result = get_best_answer(user_query, documents_with_source)
        result['documents'] = doc_summary
        
        print(f"Result: {result['confidence']}% confidence from {result.get('source_file', 'None')}")
        
        return jsonify(result)
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'answer': f'Error: {str(e)[:80]}',
            'source': 'Error',
            'confidence': 0,
            'source_file': 'None',
            'match_type': 'error'
        })

@app.route('/documents', methods=['GET'])
def get_documents():
    """Get list of available documents."""
    try:
        docs = []
        total_size = 0
        
        for filename in os.listdir(UPLOAD_FOLDER):
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            if os.path.isfile(filepath):
                file_size = os.path.getsize(filepath)
                total_size += file_size
                ext = os.path.splitext(filename)[1].lower()
                
                # Get word count if cached
                word_count = 0
                if filename in document_cache:
                    content = document_cache[filename]
                    if content and len(content.strip()) > 10:
                        word_count = len(content.split())
                
                docs.append({
                    'name': filename,
                    'size': file_size,
                    'size_kb': round(file_size / 1024, 2),
                    'type': ext[1:].upper() if ext else 'Unknown',
                    'word_count': word_count,
                    'uploaded': datetime.fromtimestamp(os.path.getmtime(filepath)).isoformat()
                })
        
        return jsonify({
            'documents': docs,
            'total_files': len(docs),
            'total_size_kb': round(total_size / 1024, 2)
        })
    
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/debug', methods=['GET'])
def debug_info():
    """Debug endpoint to see what's in cache."""
    return jsonify({
        'cache_size': len(document_cache),
        'cached_files': list(document_cache.keys()),
        'upload_folder': os.listdir(UPLOAD_FOLDER),
        'moviepy_available': MOVIEPY_AVAILABLE
    })

if __name__ == '__main__':
    print("=" * 60)
    print("Smart Document Chatbot Started")
    print("=" * 60)
    print(f"Supported formats: TXT, PDF, DOCX, MP4, MKV, MOV, AVI, FLV, WEBM")
    print(f"MoviePy available: {MOVIEPY_AVAILABLE}")
    print(f"Document folder: {os.path.abspath(UPLOAD_FOLDER)}")
    print(f"Access at: http://localhost:5000")
    print("=" * 60)
    
    # Pre-load documents
    print("Loading documents...")
    try:
        documents, summary = load_documents()
        print(f"Loaded {len(documents)} documents with content")
    except Exception as e:
        print(f"Error loading documents: {e}")
    
    app.run(debug=True, port=5000, use_reloader=False)