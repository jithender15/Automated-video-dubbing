"""
Unit tests for Translation module and segment handling.
"""

from src.config import DubbingConfig
from src.transcriber import TranscriptSegment
from src.translator import (
    MockTranslatorBackend,
    TranslatedSegment,
    Translator,
)


def test_translated_segment_serialization():
    seg = TranslatedSegment(
        id=1,
        start=0.0,
        end=3.5,
        original_text="Hallo Welt",
        translated_text="Hello World",
    )
    data = seg.to_dict()
    assert data["id"] == 1
    assert data["start"] == 0.0
    assert data["end"] == 3.5
    assert data["original_text"] == "Hallo Welt"
    assert data["translated_text"] == "Hello World"

    restored = TranslatedSegment.from_dict(data)
    assert restored.id == seg.id
    assert restored.start == seg.start
    assert restored.end == seg.end
    assert restored.original_text == seg.original_text
    assert restored.translated_text == seg.translated_text


def test_mock_translator_backend():
    backend = MockTranslatorBackend(prefix="[EN] ")
    translated = backend.translate_text("Bonjour le monde", "fr", "en")
    assert translated == "[EN] Bonjour le monde"

    # If already English, return as-is
    en_text = backend.translate_text("Already English", "en", "en")
    assert en_text == "Already English"


def test_translator_orchestrator_mock(tmp_path):
    config = DubbingConfig(temp_dir=tmp_path, translation_backend="mock")
    translator = Translator(config)

    input_segments = [
        TranscriptSegment(id=0, start=0.0, end=2.0, text="Guten Morgen"),
        TranscriptSegment(id=1, start=2.5, end=5.0, text="Wie geht es Ihnen?"),
    ]

    cache_file = tmp_path / "test_translated.json"
    translated_segments = translator.translate_segments(
        segments=input_segments,
        source_language="de",
        cache_path=cache_file,
    )

    assert len(translated_segments) == 2
    assert translated_segments[0].start == 0.0
    assert translated_segments[0].end == 2.0
    assert translated_segments[0].original_text == "Guten Morgen"
    assert "[EN] Guten Morgen" in translated_segments[0].translated_text
    assert cache_file.is_file()

    # Re-reading from cache
    reloaded = translator.translate_segments(
        segments=input_segments,
        source_language="de",
        cache_path=cache_file,
    )
    assert len(reloaded) == 2
    assert reloaded[0].translated_text == translated_segments[0].translated_text
