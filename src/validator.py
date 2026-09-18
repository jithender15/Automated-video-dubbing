"""
Output validation module for verifying final dubbed MP4 container integrity,
stream sync, audio/video duration match, and playback validity.
"""

from dataclasses import dataclass, field
import json
import logging
from pathlib import Path
import subprocess
from typing import List, Optional

from src.config import DubbingConfig
from src.utils import format_time


logger = logging.getLogger("dubbing")


@dataclass
class ValidationReport:
    file_exists: bool
    file_size_bytes: int
    video_stream_valid: bool
    audio_stream_valid: bool
    video_duration: float
    audio_duration: float
    duration_difference: float
    video_codec: str
    audio_codec: str
    resolution: str
    frame_rate: str
    playable: bool
    decode_errors: str
    passed: bool
    errors: List[str] = field(default_factory=list)

    def summary(self) -> str:
        """Return a structured summary matching Phase 11 specifications."""
        lines = [
            "\n=============================================",
            "              OUTPUT VALIDATION",
            "=============================================",
            f"File Exists:         {'PASS' if self.file_exists else 'FAIL'}",
            f"File Size:           {self.file_size_bytes / (1024 * 1024):.2f} MB",
            f"Video Stream:        {'PASS' if self.video_stream_valid else 'FAIL'} ({self.video_codec}, {self.resolution} @ {self.frame_rate})",
            f"Audio Stream:        {'PASS' if self.audio_stream_valid else 'FAIL'} ({self.audio_codec})",
            f"Video Duration:      {format_time(self.video_duration)} ({self.video_duration:.3f}s)",
            f"Audio Duration:      {format_time(self.audio_duration)} ({self.audio_duration:.3f}s)",
            f"Duration Difference: {self.duration_difference:.3f}s",
            f"Playable:            {'PASS' if self.playable else 'FAIL'}",
        ]
        if not self.playable and self.decode_errors:
            lines.append(f"Decode Errors:       {self.decode_errors}")
        if self.errors:
            lines.append("Validation Issues:")
            for err in self.errors:
                lines.append(f"  - {err}")
        status = "PASS - 100% VALID & PLAYABLE" if self.passed else "FAIL - INVALID MEDIA"
        lines.append(f"Overall Result:      {status}")
        lines.append("=============================================\n")
        return "\n".join(lines)

    def print_summary(self) -> None:
        """Print the structured terminal summary."""
        print(self.summary())


class OutputValidator:
    """Automated validator for synthesized dubbed video outputs."""

    def __init__(self, config: DubbingConfig):
        self.config = config

    def validate(
        self,
        output_path: Path,
        expected_min_duration: Optional[float] = None,
        max_duration_diff: float = 0.5,
    ) -> ValidationReport:
        """
        Thoroughly validate the final MP4 output.
        Checks container metadata, stream existence, duration drift, and executes a decode pass.
        """
        errors: List[str] = []

        if not output_path.is_file():
            errors.append("File does not exist on disk")
            report = ValidationReport(
                file_exists=False,
                file_size_bytes=0,
                video_stream_valid=False,
                audio_stream_valid=False,
                video_duration=0.0,
                audio_duration=0.0,
                duration_difference=999.0,
                video_codec="none",
                audio_codec="none",
                resolution="0x0",
                frame_rate="0",
                playable=False,
                decode_errors="File does not exist on disk",
                passed=False,
                errors=errors,
            )
            return report

        size = output_path.stat().st_size
        if size == 0:
            errors.append("File size is 0 bytes")
            report = ValidationReport(
                file_exists=True,
                file_size_bytes=0,
                video_stream_valid=False,
                audio_stream_valid=False,
                video_duration=0.0,
                audio_duration=0.0,
                duration_difference=999.0,
                video_codec="none",
                audio_codec="none",
                resolution="0x0",
                frame_rate="0",
                playable=False,
                decode_errors="File is 0 bytes",
                passed=False,
                errors=errors,
            )
            return report

        # FFprobe stream inspection
        probe_cmd = [
            self.config.ffprobe_path,
            "-v", "error",
            "-show_entries", "stream=codec_name,duration,nb_frames,width,height,r_frame_rate,sample_rate,channels",
            "-show_entries", "format=duration,size",
            "-of", "json",
            str(output_path),
        ]
        try:
            probe_res = subprocess.run(probe_cmd, capture_output=True, text=True, check=True)
            probe_data = json.loads(probe_res.stdout)
        except Exception as e:
            errors.append(f"FFprobe metadata read failed: {e}")
            report = ValidationReport(
                file_exists=True,
                file_size_bytes=size,
                video_stream_valid=False,
                audio_stream_valid=False,
                video_duration=0.0,
                audio_duration=0.0,
                duration_difference=999.0,
                video_codec="corrupt",
                audio_codec="corrupt",
                resolution="0x0",
                frame_rate="0",
                playable=False,
                decode_errors=f"FFprobe failed: {e}",
                passed=False,
                errors=errors,
            )
            return report

        streams = probe_data.get("streams", [])
        video_stream = next((s for s in streams if s.get("width")), None)
        audio_stream = next((s for s in streams if s.get("sample_rate")), None)

        video_valid = video_stream is not None
        audio_valid = audio_stream is not None

        if not video_valid:
            errors.append("No valid video stream detected")
        if not audio_valid:
            errors.append("No valid audio stream detected")

        format_dur = float(probe_data.get("format", {}).get("duration", 0.0) or 0.0)
        v_dur = float(video_stream.get("duration", format_dur) or format_dur) if video_stream else 0.0
        a_dur = float(audio_stream.get("duration", format_dur) or format_dur) if audio_stream else 0.0

        v_codec = video_stream.get("codec_name", "unknown") if video_stream else "none"
        a_codec = audio_stream.get("codec_name", "unknown") if audio_stream else "none"
        res = f"{video_stream.get('width', 0)}x{video_stream.get('height', 0)}" if video_stream else "0x0"
        fps = video_stream.get("r_frame_rate", "unknown") if video_stream else "0"

        diff = abs(v_dur - a_dur)
        if diff > max_duration_diff:
            errors.append(
                f"Audio/Video duration difference ({diff:.3f}s) exceeds max tolerance ({max_duration_diff:.3f}s)"
            )

        if expected_min_duration and v_dur < (expected_min_duration - 1.0):
            errors.append(
                f"Video duration ({v_dur:.2f}s) is shorter than expected source duration ({expected_min_duration:.2f}s)"
            )

        # Full FFmpeg stream decode test to confirm playability
        decode_cmd = [
            self.config.ffmpeg_path,
            "-v", "error",
            "-i", str(output_path),
            "-f", "null",
            "-",
        ]
        dec_res = subprocess.run(decode_cmd, capture_output=True, text=True, check=False)
        playable = (dec_res.returncode == 0)
        decode_errs = dec_res.stderr.strip()
        if not playable:
            errors.append(f"FFmpeg decode check failed: {decode_errs or 'unknown decode error'}")

        passed = len(errors) == 0

        report = ValidationReport(
            file_exists=True,
            file_size_bytes=size,
            video_stream_valid=video_valid,
            audio_stream_valid=audio_valid,
            video_duration=v_dur,
            audio_duration=a_dur,
            duration_difference=diff,
            video_codec=v_codec,
            audio_codec=a_codec,
            resolution=res,
            frame_rate=fps,
            playable=playable,
            decode_errors=decode_errs,
            passed=passed,
            errors=errors,
        )

        return report
