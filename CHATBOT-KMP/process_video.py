import os
import sys
import speech_recognition as sr
from datetime import datetime

# Support for different MoviePy versions
try:
    from moviepy import VideoFileClip
except ImportError:
    try:
        from moviepy.editor import VideoFileClip
    except ImportError:
        print("ERROR: MoviePy not installed!")
        sys.exit(1)

def extract_audio_and_text(video_path, output_audio_path, output_text_path):
    """
    Extract audio from video file and convert to text.
    
    Args:
        video_path: Path to the video file
        output_audio_path: Path to save the extracted audio
        output_text_path: Path to save the transcribed text
    """
    
    print(f"Processing video: {video_path}")
    print("=" * 60)
    
    # Step 1: Extract audio from video
    print("\n[STEP 1] Extracting audio from video...")
    try:
        video = VideoFileClip(video_path)
        
        if video.audio is None:
            print("ERROR: Video has no audio track!")
            return False
        
        print(f"Video duration: {video.duration:.2f} seconds")
        print(f"Audio channels: {video.audio.nchannels}")
        print(f"Audio frame rate: {video.audio.fps} Hz")
        
        # Extract audio
        video.audio.write_audiofile(output_audio_path, codec='pcm_s16le')
        video.close()
        
        audio_size = os.path.getsize(output_audio_path) / (1024 * 1024)
        print(f"✓ Audio extracted successfully: {output_audio_path}")
        print(f"  File size: {audio_size:.2f} MB")
        
    except Exception as e:
        print(f"ERROR extracting audio: {e}")
        return False
    
    # Step 2: Convert audio to text
    print("\n[STEP 2] Converting audio to text...")
    print("This may take a while depending on audio length...")
    print("Processing audio in chunks (this is normal for large files)...\n")
    
    try:
        recognizer = sr.Recognizer()
        transcript_text = ""
        
        # Process audio file in chunks for large files
        with sr.AudioFile(output_audio_path) as source:
            print(f"Loading audio file: {output_audio_path}")
            
            # Get duration and process in chunks
            duration = source.DURATION
            chunk_size = 60  # Process 60 seconds at a time
            num_chunks = int(duration / chunk_size) + 1
            
            print(f"Audio duration: {duration:.1f} seconds")
            print(f"Processing in {num_chunks} chunks...")
            
            for i in range(0, int(duration), chunk_size):
                try:
                    print(f"  Processing chunk {i//chunk_size + 1}/{num_chunks} ({i}-{min(i+chunk_size, int(duration))} sec)...")
                    
                    # Record audio for this chunk
                    audio_data = recognizer.record(source, duration=min(chunk_size, duration - i))
                    
                    # Recognize speech
                    try:
                        text = recognizer.recognize_google(audio_data)
                        transcript_text += text + " "
                        print(f"    ✓ Chunk recognized")
                        
                    except sr.UnknownValueError:
                        print(f"    ⚠ Chunk could not be understood")
                        transcript_text += "[inaudible] "
                        
                    except sr.RequestError as e:
                        print(f"    ⚠ Service error: {str(e)[:50]}")
                        transcript_text += "[error] "
                
                except Exception as e:
                    print(f"    ✗ Error processing chunk: {str(e)[:50]}")
                    break
            
            if transcript_text.strip():
                print("✓ Audio transcribed successfully!")
            else:
                print("⚠ No text could be extracted from audio")
                transcript_text = "[Unable to transcribe audio]"
        
        # Step 3: Save transcript to file
        print("\n[STEP 3] Saving transcript to file...")
        
        with open(output_text_path, 'w', encoding='utf-8') as f:
            f.write("[VIDEO TRANSCRIPT]\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Source: {os.path.basename(video_path)}\n")
            f.write("=" * 60 + "\n\n")
            f.write(transcript_text)
        
        print(f"✓ Transcript saved: {output_text_path}")
        
        # Display preview
        preview = transcript_text[:200] if len(transcript_text) > 200 else transcript_text
        print(f"\nTranscript preview:\n{preview}...")
        
        return True
        
    except Exception as e:
        print(f"ERROR converting audio to text: {e}")
        return False

if __name__ == '__main__':
    # Paths
    documents_folder = 'documents'
    video_file = os.path.join(documents_folder, 'video.mp4')
    audio_file = os.path.join(documents_folder, 'video_audio.wav')
    transcript_file = os.path.join(documents_folder, 'video_transcript.txt')
    
    # Check if video exists
    if not os.path.exists(video_file):
        print(f"ERROR: Video file not found: {video_file}")
        sys.exit(1)
    
    print("\n" + "=" * 60)
    print("VIDEO TO TEXT CONVERTER")
    print("=" * 60)
    
    # Process video
    success = extract_audio_and_text(video_file, audio_file, transcript_file)
    
    if success:
        print("\n" + "=" * 60)
        print("✓ PROCESSING COMPLETE!")
        print("=" * 60)
        print(f"\nGenerated files:")
        print(f"  1. Audio: {audio_file}")
        print(f"  2. Transcript: {transcript_file}")
        print(f"\nYou can now run the Flask app and ask questions about the video content!")
        print("Command: python app.py")
    else:
        print("\n" + "=" * 60)
        print("✗ PROCESSING FAILED!")
        print("=" * 60)
        sys.exit(1)