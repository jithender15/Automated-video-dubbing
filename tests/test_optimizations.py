"""
Unit tests for Long-Video Optimizations:
- Whisper model lazy loading and memory release
- Incremental translation resumption and parallel translation
- Concurrent TTS synthesis with order preservation
- Multi-threaded synchronization and intermediate file cleanup
"""

import asyncio
from pathlib import Path
import wave

from src.config import DubbingConfig
from src.synchronizer import Synchronizer, SynchronizedSegment
from src.synthesizer import Synthesizer, TTSSegment
from src.transcriber import Transcriber, TranscriptSegment
from src.translator import Translator, TranslatedSegment


def test_transcriber_unload_model():
    """Verify that unload_model releases cached Whisper reference."""
    Transcriber._cached_model = "fake_model"
    Transcriber._cached_model_name = "test_model"

    Transcriber.unload_model()

    assert Transcriber._cached_model is None
    assert Transcriber._cached_model_name is None


def test_translator_incremental_resumption(tmp_path):
    """Verify that Translator reuses existing partial translations and only translates missing segments."""
    config = DubbingConfig(translation_backend="mock")
    translator = Translator(config)

    segments = [
        TranscriptSegment(id=0, start=0.0, end=2.0, text="Eins"),
        TranscriptSegment(id=1, start=2.0, end=4.0, text="Zwei"),
        TranscriptSegment(id=2, start=4.0, end=6.0, text="Drei"),
    ]

    cache_file = tmp_path / "translated_partial.json"
    # Pre-seed cache with segment 0 already translated
    from src.utils import save_json
    save_json([{"id": 0, "start": 0.0, "end": 2.0, "original_text": "Eins", "translated_text": "One"}], cache_file)

    results = translator.translate_segments(
        segments=segments,
        source_language="de",
        cache_path=cache_file,
    )

    assert len(results) == 3
    assert results[0].translated_text == "One"  # From pre-seeded cache
    assert "[EN]" in results[1].translated_text  # Translated by mock backend
    assert "[EN]" in results[2].translated_text  # Translated by mock backend


def test_synthesizer_concurrent_caching(tmp_path, monkeypatch):
    """Verify that Synthesizer concurrent synthesis runs and preserves segment ordering."""
    config = DubbingConfig(tts_voice="en-US-AriaNeural")
    synth = Synthesizer(config)

    segments = [
        TranslatedSegment(id=0, start=0.0, end=1.0, original_text="One", translated_text="One"),
        TranslatedSegment(id=1, start=1.0, end=2.0, original_text="Two", translated_text="Two"),
        TranslatedSegment(id=2, start=2.0, end=3.0, original_text="Three", translated_text="Three"),
    ]

    # Mock single segment synthesis to create small dummy MP3 files
    async def mock_save(text, output_file, voice, rate="+0%", pitch="+0Hz"):
        output_file.write_bytes(b"ID3" + b"\x00" * 1000)

    monkeypatch.setattr(synth, "_synthesize_single_segment", mock_save)

    tts_segs = synth.synthesize_all(segments, output_dir=tmp_path / "tts", concurrency=3)

    assert len(tts_segs) == 3
    assert [s.id for s in tts_segs] == [0, 1, 2]
    for seg in tts_segs:
        assert seg.audio_path.is_file()
        assert seg.audio_path.stat().st_size > 500


def test_synchronizer_parallel_and_cleanup(tmp_path):
    """Verify multi-threaded synchronization and intermediate file cleanup."""
    config = DubbingConfig(temp_dir=tmp_path, sample_rate=16000)
    syncer = Synchronizer(config)

    # Create 3 dummy audio segments
    dummy_wav = tmp_path / "dummy.wav"
    with wave.open(str(dummy_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * 16000)  # 1.0s of audio

    tts_segs = [
        TTSSegment(id=0, start=0.0, end=1.0, audio_path=dummy_wav, text="A"),
        TTSSegment(id=1, start=2.0, end=3.0, audio_path=dummy_wav, text="B"),
        TTSSegment(id=2, start=4.0, end=5.0, audio_path=dummy_wav, text="C"),
    ]

    out_wav = tmp_path / "final_dubbed.wav"
    result = syncer.synchronize(
        tts_segments=tts_segs,
        total_duration=6.0,
        temp_dir=tmp_path,
        output_wav_path=out_wav,
        cleanup_intermediates=True,
    )

    assert result.is_file()
    assert result.stat().st_size > 0

    # Intermediate sync_segments directory should have had its WAV files cleaned up
    sync_dir = tmp_path / "sync_segments"
    remaining_wavs = list(sync_dir.glob("*.wav"))
    assert len(remaining_wavs) == 0
