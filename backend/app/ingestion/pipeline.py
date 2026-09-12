"""Docling-based document parsing and structure-aware chunking."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from functools import lru_cache
from app.config import settings


@dataclass
class ChunkData:
    raw_text: str
    retrieval_text: str  # contextualized: section heading prepended
    section_title: str
    page_numbers: list[int]
    chunk_index: int


SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".pptx", ".md", ".markdown", ".html", ".htm"}

EXTENSION_TO_CONTENT_TYPE: dict[str, str] = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".html": "text/html",
    ".htm": "text/html",
}


def validate_and_detect_type(filename: str) -> str:
    """Return canonical content-type or raise ValueError for unsupported extensions."""
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type '{ext}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )
    return EXTENSION_TO_CONTENT_TYPE[ext]


@lru_cache(maxsize=1)
def _get_chunker():
    """Lazy-loaded chunker singleton — model downloaded on first call."""
    from transformers import AutoTokenizer
    from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
    from docling.chunking import HybridChunker

    hf_tok = HuggingFaceTokenizer(
        tokenizer=AutoTokenizer.from_pretrained(settings.DENSE_EMBEDDING_MODEL),
        max_tokens=settings.MAX_TOKENS_PER_CHUNK,
    )
    return HybridChunker(tokenizer=hf_tok)


def parse_and_chunk(file_path: Path, content_type: str) -> list[ChunkData]:
    """
    Convert a document with Docling and produce structure-aware chunks.

    raw_text:      faithful extracted evidence for citations/answers
    retrieval_text: contextualized text (headings prepended) for embedding
    """
    from docling.document_converter import DocumentConverter

    converter = DocumentConverter()
    result = converter.convert(str(file_path))

    if result.document is None:
        raise ValueError("Docling failed to parse document — result.document is None")

    chunker = _get_chunker()
    raw_chunks = list(chunker.chunk(dl_doc=result.document))

    output: list[ChunkData] = []
    for i, chunk in enumerate(raw_chunks):
        raw_text = chunk.text.strip()
        if not raw_text:
            continue

        headings: list[str] = list(getattr(chunk.meta, "headings", None) or [])
        section_title = " > ".join(headings) if headings else ""

        page_numbers: list[int] = []
        for item in (getattr(chunk.meta, "doc_items", None) or []):
            for prov in (getattr(item, "prov", None) or []):
                page_no = getattr(prov, "page_no", None)
                if page_no is not None:
                    page_numbers.append(page_no)
        page_numbers = sorted(set(page_numbers))

        try:
            retrieval_text = chunker.serialize(chunk=chunk)
        except Exception:
            retrieval_text = raw_text
        if not retrieval_text.strip():
            retrieval_text = raw_text

        output.append(ChunkData(
            raw_text=raw_text,
            retrieval_text=retrieval_text,
            section_title=section_title,
            page_numbers=page_numbers,
            chunk_index=len(output),  # compact sequential index
        ))

    if not output:
        raise ValueError("Document produced no text chunks after parsing")

    return output
