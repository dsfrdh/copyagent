"""Document loader: .md, .txt, .docx, .pdf."""
from pathlib import Path

def load_file(file_path: str) -> str:
    """Load a single file and return its text content."""
    fp = Path(file_path)
    suffix = fp.suffix.lower()

    if suffix == ".txt":
        return fp.read_text(encoding="utf-8")
    elif suffix == ".md":
        return fp.read_text(encoding="utf-8")
    elif suffix == ".docx":
        from docx import Document  # type: ignore
        doc = Document(str(fp))
        return "\n".join(p.text for p in doc.paragraphs)
    elif suffix == ".pdf":
        from PyPDF2 import PdfReader  # type: ignore
        reader = PdfReader(str(fp))
        return "\n".join(
            page.extract_text() or ""
            for page in reader.pages
        )
    else:
        raise ValueError(f"Unsupported file type: {suffix}")

def load_directory(dir_path: str) -> list[dict]:
    """Load all supported files from a directory. Returns [{title, file_path, text}]."""
    results = []
    supported = {".txt", ".md", ".docx", ".pdf"}
    for fp in Path(dir_path).iterdir():
        if fp.suffix.lower() in supported:
            try:
                text = load_file(str(fp))
                results.append({
                    "title": fp.stem,
                    "file_path": str(fp),
                    "text": text
                })
            except Exception as e:
                print(f"Warning: failed to load {fp.name}: {e}")
    return results
