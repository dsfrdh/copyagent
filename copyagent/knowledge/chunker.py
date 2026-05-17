"""Text chunking with semantic boundary awareness."""
import re

def split_chunks(text: str, chunk_size: int = 800, overlap: int = 150) -> list[str]:
    """Split text into overlapping chunks, respecting paragraph boundaries."""
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    chunks = []
    current = ""
    for p in paragraphs:
        if len(current) + len(p) + 1 <= chunk_size:
            current = (current + "\n" + p).strip()
        else:
            if current:
                chunks.append(current)
            # If a single paragraph exceeds chunk_size, force-split by sentences
            if len(p) > chunk_size:
                sentences = re.split(r"(?<=[。！？.!?])", p)
                sub = ""
                for s in sentences:
                    if len(sub) + len(s) <= chunk_size:
                        sub += s
                    else:
                        if sub:
                            chunks.append(sub)
                        sub = s
                if sub:
                    current = sub
                else:
                    current = ""
            else:
                current = p

    if current:
        chunks.append(current)

    # Apply overlap: prepend tail of previous chunk
    if overlap > 0 and len(chunks) > 1:
        overlapped = [chunks[0]]
        for i in range(1, len(chunks)):
            prev = chunks[i - 1]
            tail = prev[-overlap:] if len(prev) > overlap else prev
            overlapped.append(tail + "\n" + chunks[i])
        chunks = overlapped

    return chunks
