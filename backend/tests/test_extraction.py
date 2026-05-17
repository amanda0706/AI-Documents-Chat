from backend.app.extraction import has_meaningful_text


def test_meaningful_text_requires_real_content() -> None:
    assert has_meaningful_text(["", "short"]) is False
    assert has_meaningful_text(["Payment terms are net 30 days from invoice receipt."]) is True
