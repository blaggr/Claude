from src.chunker import chunk_text
from src.config import settings


def test_chunk_basic_paragraphs():
    text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
    chunks = list(chunk_text(text))
    assert len(chunks) == 1
    assert "First paragraph" in chunks[0].text
    assert "Third paragraph" in chunks[0].text


def test_chunk_long_text_splits():
    long_para = ("word " * 4000).strip()
    chunks = list(chunk_text(long_para))
    assert len(chunks) > 1


def test_pdf_page_markers_preserved():
    text = "[Page 1]\nAlpha content.\n\n[Page 2]\nBeta content.\n\n[Page 3]\nGamma content."
    chunks = list(chunk_text(text))
    assert chunks[0].page_start == 1
    last = chunks[-1]
    assert last.page_end is not None and last.page_end >= 1


def test_respects_target_size_loosely():
    paragraphs = [f"Paragraph {i} " + ("token " * 100) for i in range(30)]
    text = "\n\n".join(paragraphs)
    chunks = list(chunk_text(text))
    assert len(chunks) > 1
    # No chunk should be wildly larger than target + overlap
    import tiktoken
    enc = tiktoken.get_encoding("cl100k_base")
    for c in chunks:
        assert len(enc.encode(c.text, disallowed_special=())) <= settings.chunk_tokens + 50
