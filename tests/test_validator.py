"""
Unit tests for OutputValidator.
Tests container checks, stream checks, duration drift detection,
playability verification, and error handling.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from src.config import DubbingConfig
from src.validator import OutputValidator, ValidationReport


@pytest.fixture
def validator_config(tmp_path):
    return DubbingConfig(
        project_root=tmp_path,
        download_dir=tmp_path / "downloads",
        temp_dir=tmp_path / "temp",
        output_dir=tmp_path / "outputs",
        log_dir=tmp_path / "logs",
    )


def test_validator_nonexistent_file(validator_config, tmp_path):
    validator = OutputValidator(validator_config)
    report = validator.validate(tmp_path / "nonexistent.mp4")
    assert not report.file_exists
    assert not report.passed
    assert "File does not exist on disk" in report.errors


def test_validator_zero_byte_file(validator_config, tmp_path):
    empty_file = tmp_path / "empty.mp4"
    empty_file.write_bytes(b"")
    validator = OutputValidator(validator_config)
    report = validator.validate(empty_file)
    assert report.file_exists
    assert report.file_size_bytes == 0
    assert not report.passed
    assert any("0 bytes" in e for e in report.errors)


def test_validator_valid_media(validator_config, tmp_path):
    media_file = tmp_path / "sample.mp4"
    media_file.write_bytes(b"mock_mp4_bytes")

    probe_json = (
        '{"streams": ['
        '{"codec_name": "h264", "width": 1920, "height": 1080, "r_frame_rate": "30/1", "duration": "12.5"},'
        '{"codec_name": "aac", "sample_rate": "44100", "channels": 2, "duration": "12.5"}'
        '], "format": {"duration": "12.5", "size": "1048576"}}'
    )

    validator = OutputValidator(validator_config)

    with patch("subprocess.run") as mock_run:
        # 1st call for ffprobe, 2nd for ffmpeg decode test
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=probe_json, stderr=""),
            MagicMock(returncode=0, stdout="", stderr=""),
        ]

        report = validator.validate(media_file, expected_min_duration=12.0)

    assert report.passed
    assert report.file_exists
    assert report.video_stream_valid
    assert report.audio_stream_valid
    assert report.playable
    assert report.video_duration == 12.5
    assert report.audio_duration == 12.5
    assert report.duration_difference == 0.0
    assert "PASS" in report.summary()


def test_validator_duration_drift_failure(validator_config, tmp_path):
    media_file = tmp_path / "drift.mp4"
    media_file.write_bytes(b"mock_mp4_bytes")

    # Audio is 2 seconds shorter than video
    probe_json = (
        '{"streams": ['
        '{"codec_name": "h264", "width": 1280, "height": 720, "r_frame_rate": "30/1", "duration": "15.0"},'
        '{"codec_name": "aac", "sample_rate": "44100", "channels": 2, "duration": "13.0"}'
        '], "format": {"duration": "15.0", "size": "1048576"}}'
    )

    validator = OutputValidator(validator_config)

    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=probe_json, stderr=""),
            MagicMock(returncode=0, stdout="", stderr=""),
        ]
        report = validator.validate(media_file, max_duration_diff=0.5)

    assert not report.passed
    assert any("exceeds max tolerance" in e for e in report.errors)
