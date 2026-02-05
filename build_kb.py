import os
from pypdf import PdfReader
from docx import Document

DOCUMENTS_DIR = 'documents'
KB_PATH = os.path.join(DOCUMENTS_DIR, 'knowledge_base.txt')

os.makedirs(DOCUMENTS_DIR, exist_ok=True)

def extract_text_simple(filepath):
    ext = os.path.splitext(filepath)[1].lower()
    try:
        if ext == '.txt':
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        elif ext == '.pdf':
            text = ''
            reader = PdfReader(filepath)
            for page in reader.pages:
                content = page.extract_text()
                if content:
                    text += content + '\n'
            return text
        elif ext in ['.docx', '.doc']:
            doc = Document(filepath)
            return '\n'.join([p.text for p in doc.paragraphs])
        elif ext in ['.mp4', '.mkv', '.mov', '.avi', '.flv', '.webm']:
            # Prefer existing transcript file
            base = os.path.splitext(os.path.basename(filepath))[0]
            transcript = os.path.join(DOCUMENTS_DIR, base + '_transcript.txt')
            alt = os.path.join(DOCUMENTS_DIR, 'video_transcript.txt')
            if os.path.exists(transcript):
                with open(transcript, 'r', encoding='utf-8', errors='ignore') as f:
                    return f.read()
            if os.path.exists(alt):
                with open(alt, 'r', encoding='utf-8', errors='ignore') as f:
                    return f.read()
            return ''
        else:
            return ''
    except Exception as e:
        return f"[Error reading {os.path.basename(filepath)}: {e}]"


def build_kb():
    parts = []
    files = sorted(os.listdir(DOCUMENTS_DIR))
    for fname in files:
        if fname == os.path.basename(KB_PATH):
            continue
        path = os.path.join(DOCUMENTS_DIR, fname)
        if not os.path.isfile(path):
            continue
        print(f"Processing {fname}...")
        text = extract_text_simple(path)
        if not text or text.strip() == '':
            print(f"  -> No extractable text for {fname}")
            continue
        header = f"[FROM: {fname}]\n"
        parts.append(header + text.strip() + '\n\n')

    if not parts:
        print('No documents found to build knowledge base.')
        return False

    # Write knowledge base
    with open(KB_PATH, 'w', encoding='utf-8') as kb:
        kb.write('[KNOWLEDGE BASE]\n')
        kb.write('Generated: ' + __import__('datetime').datetime.now().isoformat() + '\n\n')
        for part in parts:
            kb.write(part)
    print(f'Knowledge base written to {KB_PATH}')
    return True

if __name__ == '__main__':
    build_kb()