from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

KB_DIR = Path(__file__).resolve().parents[1] / "data" / "kb"


@dataclass(frozen=True)
class Document:
    source: str
    text: str


@dataclass(frozen=True)
class Chunk:
    id: str
    text: str
    source: str
    heading: str


def load_documents(kb_dir: Path | None = None) -> list[Document]:
    base = Path(kb_dir) if kb_dir else KB_DIR
    docs: list[Document] = []
    for path in sorted(base.glob("*.md")):
        docs.append(Document(source=path.name, text=path.read_text(encoding="utf-8")))
    return docs


def _split_sections(text: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    heading = ""
    buffer: list[str] = []
    for line in text.splitlines():
        if line.startswith("#"):
            if buffer:
                sections.append((heading, "\n".join(buffer).strip()))
                buffer = []
            heading = line.lstrip("#").strip()
        else:
            buffer.append(line)
    if buffer:
        sections.append((heading, "\n".join(buffer).strip()))
    return [(h, b) for h, b in sections if b]


def _window(text: str, size: int, overlap: int) -> list[str]:
    if len(text) <= size:
        return [text]
    pieces: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        pieces.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return [p for p in pieces if p]


def chunk_document(doc: Document, chunk_size: int = 700, overlap: int = 100) -> list[Chunk]:
    chunks: list[Chunk] = []
    for heading, body in _split_sections(doc.text):
        paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
        buffer = ""
        idx = 0
        for para in paragraphs:
            if buffer and len(buffer) + len(para) + 2 <= chunk_size:
                buffer = buffer + "\n\n" + para
                continue
            if buffer:
                chunks.append(
                    Chunk(
                        id=f"{doc.source}:{heading}:{idx}",
                        text=buffer,
                        source=doc.source,
                        heading=heading,
                    )
                )
                idx += 1
            if len(para) > chunk_size:
                for piece in _window(para, chunk_size, overlap):
                    chunks.append(
                        Chunk(
                            id=f"{doc.source}:{heading}:{idx}",
                            text=piece,
                            source=doc.source,
                            heading=heading,
                        )
                    )
                    idx += 1
                buffer = ""
            else:
                buffer = para
        if buffer:
            chunks.append(
                Chunk(
                    id=f"{doc.source}:{heading}:{idx}",
                    text=buffer,
                    source=doc.source,
                    heading=heading,
                )
            )
    return chunks


def ingest(kb_dir: Path | None = None) -> list[Chunk]:
    chunks: list[Chunk] = []
    for doc in load_documents(kb_dir):
        chunks.extend(chunk_document(doc))
    return chunks
