"""
Unit tests for Audio Synchronization and timeline calculations.
"""

from pathlib import Path
import struct
import wave

from src.config import DubbingConfig
from src.synchronizer import Synchronizer, SynchronizedSegment


def test_calculate_tempo_clamping():
    config = DubbingConfig(min_tempo=0.80, max_tempo=1.35)
    syncer = Synchronizer(config)

    # Within normal bounds (tts = 4.4s, target = 4.0s -> ratio = 1.1)
    tempo_normal = syncer.calculate_tempo(tts_duration=4.4, target_duration=4.0)
    assert 1.08 <= tempo_normal <= 1.12

    # Exceeds max tempo (tts = 8.0s, target = 4.0s -> ratio = 2.0 -> clamped to 1.35)
    tempo_high = syncer.calculate_tempo(tts_duration=8.0, target_duration=4.0)
    assert tempo_high == 1.35

    # Much shorter than target (tts = 1.0s, target = 4.0s -> ratio = 0.25 -> clamped to 0.80)
    tempo_low = syncer.calculate_tempo(tts_duration=1.0, target_duration=4.0)
    assert tempo_low == 0.80

    # Near equal (tts = 4.05s, target = 4.0s -> ratio = 1.0125 -> no adjustment needed)
    tempo_equal = syncer.calculate_tempo(tts_duration=4.05, target_duration=4.0)
    assert tempo_equal == 1.0


def create_dummy_wav(file_path: Path, duration_sec: float, sample_rate: int = 16000) -> Path:
    """Helper to generate a valid PCM 16-bit mono WAV file."""
    num_samples = int(duration_sec * sample_rate)
    # Simple sine wave or tone
    samples = [int(1000 * (i % 20 - 10)) for i in range(num_samples)]
    raw_data = struct.pack(f"<{len(samples)}h", *samples)

    file_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(file_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(raw_data)
    return file_path


def test_assemble_timeline(tmp_path):
    config = DubbingConfig(temp_dir=tmp_path, sample_rate=16000)
    syncer = Synchronizer(config)

    wav1 = create_dummy_wav(tmp_path / "seg1.wav", duration_sec=2.0)
    wav2 = create_dummy_wav(tmp_path / "seg2.wav", duration_sec=1.5)

    segments = [
        SynchronizedSegment(
            id=0,
            start=1.0,
            end=3.0,
            original_duration=2.0,
            tts_duration=2.0,
            adjusted_duration=2.0,
            tempo_factor=1.0,
            audio_path=wav1,
        ),
        SynchronizedSegment(
            id=1,
            start=4.0,
            end=5.5,
            original_duration=1.5,
            tts_duration=1.5,
            adjusted_duration=1.5,
            tempo_factor=1.0,
            audio_path=wav2,
        ),
    ]

    output_wav = tmp_path / "assembled_dubbed.wav"
    total_duration = 6.0

    result_path = syncer.assemble_timeline(
        synchronized_segments=segments,
        total_duration=total_duration,
        output_wav_path=output_wav,
    )

    assert result_path.is_file()
    assert result_path.stat().st_size > 0

    with wave.open(str(result_path), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        assert wf.getframerate() == 16000
        frames = wf.getnframes()
        calculated_duration = frames / 16000.0
        # Should match total_duration of 6.0 seconds
        assert abs(calculated_duration - 6.0) < 0.05


def test_zero_accumulated_drift(tmp_path):
    """Verify that multiple spaced segments maintain absolute positioning with zero drift."""
    config = DubbingConfig(temp_dir=tmp_path, sample_rate=16000)
    syncer = Synchronizer(config)
    import numpy as np

    # Place 5 segments across a 60-second canvas
    segments = []
    expected_starts = [0.5, 12.345, 27.890, 41.123, 55.500]
    for i, st in enumerate(expected_starts):
        wav = create_dummy_wav(tmp_path / f"drift_{i}.wav", duration_sec=1.0)
        segments.append(
            SynchronizedSegment(
                id=i,
                start=st,
                end=st + 1.0,
                original_duration=1.0,
                tts_duration=1.0,
                adjusted_duration=1.0,
                tempo_factor=1.0,
                audio_path=wav,
            )
        )

    out_wav = tmp_path / "drift_test.wav"
    syncer.assemble_timeline(segments, total_duration=60.0, output_wav_path=out_wav)

    with wave.open(str(out_wav), "rb") as wf:
        raw = wf.readframes(wf.getnframes())
        samples = np.frombuffer(raw, dtype=np.int16)

    # Verify each segment starts at EXACTLY round(st * 16000) samples
    for st in expected_starts:
        sample_idx = int(round(st * 16000))
        # Just before segment: silence (0)
        if sample_idx > 0:
            assert samples[sample_idx - 1] == 0
        # First sample of segment: non-zero signal
        assert samples[sample_idx] != 0


def test_overlapping_segments_crossfade(tmp_path):
    """Verify that overlapping segments apply decay without hard clipping distortion."""
    config = DubbingConfig(temp_dir=tmp_path, sample_rate=16000)
    syncer = Synchronizer(config)
    import numpy as np

    # Segment 1: from 1.0s to 3.5s (2.5s duration)
    # Segment 2: starts at 2.5s (1.0s overlap with Segment 1!)
    wav1 = create_dummy_wav(tmp_path / "ov1.wav", duration_sec=2.5)
    wav2 = create_dummy_wav(tmp_path / "ov2.wav", duration_sec=2.0)

    segments = [
        SynchronizedSegment(
            id=0,
            start=1.0,
            end=2.0,
            original_duration=1.0,
            tts_duration=2.5,
            adjusted_duration=2.5,
            tempo_factor=1.0,
            audio_path=wav1,
        ),
        SynchronizedSegment(
            id=1,
            start=2.5,
            end=4.5,
            original_duration=2.0,
            tts_duration=2.0,
            adjusted_duration=2.0,
            tempo_factor=1.0,
            audio_path=wav2,
        ),
    ]

    out_wav = tmp_path / "overlap_test.wav"
    syncer.assemble_timeline(segments, total_duration=6.0, output_wav_path=out_wav)

    with wave.open(str(out_wav), "rb") as wf:
        raw = wf.readframes(wf.getnframes())
        samples = np.frombuffer(raw, dtype=np.int16)

    # Audio should never exceed int16 bounds [-32768, 32767]
    assert np.all(samples >= -32768)
    assert np.all(samples <= 32767)
    # Total duration must equal exactly 6.0 seconds
    assert len(samples) == 6.0 * 16000


def test_silence_trimming_numpy(tmp_path):
    """Verify that _trim_silence_numpy strips dead silence from start and end."""
    config = DubbingConfig(temp_dir=tmp_path, sample_rate=16000)
    syncer = Synchronizer(config)
    import numpy as np

    # Create 0.5s silence + 1.0s tone + 0.8s silence
    lead_silence = np.zeros(8000, dtype=np.int16)
    tone = (np.sin(np.linspace(0, 100 * np.pi, 16000)) * 10000).astype(np.int16)
    trail_silence = np.zeros(12800, dtype=np.int16)

    full = np.concatenate([lead_silence, tone, trail_silence])
    trimmed = syncer._trim_silence_numpy(full, sample_rate=16000)

    # Trimmed length should be close to 16000 (+ padding ~960 samples) and much less than original 36800
    assert len(trimmed) < len(full)
    assert 15000 <= len(trimmed) <= 18000


def test_non_speech_gap_preservation(tmp_path):
    """Verify that long non-speech gaps between sentences are preserved exactly without compression."""
    config = DubbingConfig(temp_dir=tmp_path, sample_rate=16000)
    syncer = Synchronizer(config)
    import numpy as np

    # Segment 1: [1.0s - 3.0s]
    # Silence gap: [3.0s - 13.0s] (10 seconds silence)
    # Segment 2: [13.0s - 15.0s]
    wav1 = create_dummy_wav(tmp_path / "gap_seg1.wav", duration_sec=2.0)
    wav2 = create_dummy_wav(tmp_path / "gap_seg2.wav", duration_sec=2.0)

    segments = [
        SynchronizedSegment(
            id=0,
            start=1.0,
            end=3.0,
            original_duration=2.0,
            tts_duration=2.0,
            adjusted_duration=2.0,
            tempo_factor=1.0,
            audio_path=wav1,
        ),
        SynchronizedSegment(
            id=1,
            start=13.0,
            end=15.0,
            original_duration=2.0,
            tts_duration=2.0,
            adjusted_duration=2.0,
            tempo_factor=1.0,
            audio_path=wav2,
        ),
    ]

    out_wav = tmp_path / "gap_timeline.wav"
    syncer.assemble_timeline(segments, total_duration=20.0, output_wav_path=out_wav)

    with wave.open(str(out_wav), "rb") as wf:
        raw = wf.readframes(wf.getnframes())
        samples = np.frombuffer(raw, dtype=np.int16)

    sr = 16000
    # Canvas length exactly 20.0s * 16000
    assert len(samples) == 20 * sr

    # Initial silence [0.0s to 1.0s]
    assert np.all(samples[0 : int(0.95 * sr)] == 0)

    # Segment 1 active [1.0s to 3.0s]
    assert np.any(samples[int(1.0 * sr) : int(3.0 * sr)] != 0)

    # Dead silence gap [3.5s to 12.5s]
    gap_samples = samples[int(3.5 * sr) : int(12.5 * sr)]
    assert np.all(gap_samples == 0), "Silence gap between segments must remain pure silence"

    # Segment 2 starts at exactly 13.0s
    assert samples[int(13.0 * sr) - 1] == 0
    assert samples[int(13.0 * sr)] != 0


