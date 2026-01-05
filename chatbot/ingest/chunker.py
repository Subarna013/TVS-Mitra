# chatbot/ingest/chunker.py

def chunk_text(
    text: str,
    chunk_size: int = 400,
    overlap: int = 80,
    min_chunk_size: int = 50
) -> list[str]:
    """
    Split text into overlapping word chunks.

    - chunk_size: number of words per chunk
    - overlap: number of overlapping words
    - min_chunk_size: drop very small tail chunks
    """

    if not text or not text.strip():
        return []

    # Safety: prevent infinite loop
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    # Normalize whitespace
    text = " ".join(text.split())
    words = text.split()

    # Small document → single chunk
    if len(words) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    step = chunk_size - overlap

    while start < len(words):
        end = start + chunk_size
        chunk_words = words[start:end]

        # Drop tiny trailing chunks
        if len(chunk_words) < min_chunk_size:
            break

        chunks.append(" ".join(chunk_words))
        start += step

    return chunks
