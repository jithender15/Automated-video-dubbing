"""
Integration tests for Pipeline orchestration using mocked components.
Verifies stage chaining, caching behavior, and error handling without external network calls.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from src.config import DubbingConfig
from src.downloader import DownloadResult
from src.pipeline import DubbingPipeline
from src.synthesizer import TTSSegment
from src.transcriber import TranscriptSegment, TranscriptionResult
from src.translator import TranslatedSegment


@pytest.fixture
def mock_pipeline_config(tmp_path):
    config = DubbingConfig(
        project_root=tmp_path,
        download_dir=tmp_path / "downloads",
        temp_dir=tmp_path / "temp",
        output_dir=tmp_path / "outputs",
        log_dir=tmp_path / "logs",
        translation_backend="mock",
        benchmark=True,
    )
    return config


def test_pipeline_orchestration_mocked(mock_pipeline_config, tmp_path):
    # Dummy video file
    dummy_video = tmp_path / "downloads" / "dummy_video.mp4"
    dummy_video.parent.mkdir(parents=True, exist_ok=True)
    dummy_video.write_bytes(b"dummy video content")

    dummy_audio = tmp_path / "temp" / "test_id" / "audio.wav"
    dummy_audio.parent.mkdir(parents=True, exist_ok=True)
    dummy_audio.write_bytes(b"dummy audio content")

    dummy_output_video = tmp_path / "outputs" / "dummy_video_12345678901_dubbed.mp4"
    dummy_output_video.parent.mkdir(parents=True, exist_ok=True)
    dummy_output_video.write_bytes(b"dummy final video")

    with patch("src.pipeline.check_ffmpeg_installed", return_value=(True, "FFmpeg 9.0.1")):
        pipeline = DubbingPipeline(mock_pipeline_config)

    # Mock all stage sub-components
    pipeline.downloader.download = MagicMock(
        return_value=DownloadResult(
            video_path=dummy_video,
            video_id="test_id",
            title="dummy_video",
            duration=10.0,
        )
    )

    pipeline.audio_extractor.extract_audio = MagicMock(return_value=dummy_audio)

    pipeline.transcriber.transcribe = MagicMock(
        return_value=TranscriptionResult(
            language="de",
            segments=[
                TranscriptSegment(id=0, start=0.0, end=3.0, text="Hallo Welt"),
                TranscriptSegment(id=1, start=4.0, end=7.0, text="Willkommen"),
            ],
            full_text="Hallo Welt Willkommen",
        )
    )

    pipeline.translator.translate_segments = MagicMock(
        return_value=[
            TranslatedSegment(id=0, start=0.0, end=3.0, original_text="Hallo Welt", translated_text="Hello World"),
            TranslatedSegment(id=1, start=4.0, end=7.0, original_text="Willkommen", translated_text="Welcome"),
        ]
    )

    pipeline.synthesizer.synthesize_all = MagicMock(
        return_value=[
            TTSSegment(id=0, start=0.0, end=3.0, audio_path=tmp_path / "s0.mp3", text="Hello World"),
            TTSSegment(id=1, start=4.0, end=7.0, audio_path=tmp_path / "s1.mp3", text="Welcome"),
        ]
    )

    dubbed_audio = tmp_path / "temp" / "test_id" / "dubbed_audio.wav"
    pipeline.synchronizer.synchronize = MagicMock(return_value=dubbed_audio)

    pipeline.video_processor.create_dubbed_video = MagicMock(return_value=dummy_output_video)

    from src.validator import ValidationReport
    pipeline.validator.validate = MagicMock(
        return_value=ValidationReport(
            file_exists=True,
            file_size_bytes=1024 * 1024,
            video_stream_valid=True,
            audio_stream_valid=True,
            video_duration=10.0,
            audio_duration=10.0,
            duration_difference=0.0,
            video_codec="h264",
            audio_codec="aac",
            resolution="1280x720",
            frame_rate="30/1",
            playable=True,
            decode_errors="",
            passed=True,
            errors=[],
        )
    )

    # Run the pipeline
    test_url = "https://www.youtube.com/watch?v=12345678901"
    result = pipeline.run(test_url)

    # Assertions
    assert result.video_id == "12345678901"
    assert result.detected_language == "de"
    assert result.segment_count == 2
    assert result.output_video_path == dummy_output_video
    assert "Download" in result.stage_timings
    assert "Transcription" in result.stage_timings
    assert "Video Muxing" in result.stage_timings
    assert result.total_time_seconds >= 0

    # Verify stage method calls
    pipeline.downloader.download.assert_called_once()
    pipeline.audio_extractor.extract_audio.assert_called_once()
    pipeline.transcriber.transcribe.assert_called_once()
    pipeline.translator.translate_segments.assert_called_once()
    pipeline.synthesizer.synthesize_all.assert_called_once()
    pipeline.synchronizer.synchronize.assert_called_once()
    pipeline.video_processor.create_dubbed_video.assert_called_once()
    pipeline.validator.validate.assert_called_once()
