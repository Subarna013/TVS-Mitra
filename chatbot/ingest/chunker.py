# chatbot/ingest/chunker.py

def chunk_text(text: str, chunk_size: int = 400, overlap: int = 80) -> list[str]:
    if not text or not text.strip():
        return []

    words = text.split()

    if len(words) <= chunk_size:
        return [" ".join(words)]

    chunks = []
    start = 0

    while start < len(words):
        end = start + chunk_size
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        start += chunk_size - overlap

    return chunks
