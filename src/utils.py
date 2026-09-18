"""
Utility helpers for logging, formatting, media inspection, and FFmpeg validation.
"""

import json
import logging
from pathlib import Path
import re
import subprocess
import time
from typing import Any, Dict, Optional, Tuple


def setup_logger(log_dir: Path, name: str = "dubbing") -> logging.Logger:
    """Set up structured logging to both terminal and a rotating log file."""
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # Avoid duplicate handlers if setup_logger is called multiple times
    if logger.handlers:
        return logger

    # File handler records detailed debug information
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    file_handler = logging.FileHandler(
        log_dir / f"{name}_{timestamp}.log", encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(filename)s:%(lineno)d] %(message)s"
    )
    file_handler.setFormatter(file_fmt)

    # Console handler records informative messages
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_fmt = logging.Formatter("%(message)s")
    console_handler.setFormatter(console_fmt)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger


def check_ffmpeg_installed(ffmpeg_path: str = "ffmpeg") -> Tuple[bool, str]:
    """
    Verify that FFmpeg is accessible and executable.
    Returns (True, version_string) on success or (False, error_message) on failure.
    """
    try:
        result = subprocess.run(
            [ffmpeg_path, "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode == 0:
            first_line = result.stdout.splitlines()[0] if result.stdout else "FFmpeg"
            return True, first_line
        return False, f"FFmpeg returned exit code {result.returncode}: {result.stderr.strip()}"
    except FileNotFoundError:
        return (
            False,
            "FFmpeg executable not found in PATH or configured location.\n"
            "Please install FFmpeg and make sure it is available in PATH:\n"
            "  Windows: winget install Gyan.FFmpeg.Essentials\n"
            "  macOS: brew install ffmpeg\n"
            "  Linux: sudo apt install ffmpeg",
        )
    except Exception as e:
        return False, f"Failed to execute FFmpeg: {str(e)}"


def get_media_duration(
    file_path: Path,
    ffprobe_path: str = "ffprobe",
    ffmpeg_path: str = "ffmpeg",
    stream_type: Optional[str] = None,
) -> float:
    """
    Probe the duration of a video or audio file in seconds using ffprobe.
    If stream_type is specified (e.g. 'v' or 'a'), probes that stream specifically.
    Falls back to container format duration and ffmpeg stderr parsing.
    """
    if not file_path.is_file():
        raise FileNotFoundError(f"Media file not found: {file_path}")

    # 1. Try ffprobe stream duration if stream_type specified
    if stream_type:
        st_filter = f"{stream_type[0]}:0"
        try:
            cmd = [
                ffprobe_path,
                "-v", "error",
                "-select_streams", st_filter,
                "-show_entries", "stream=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(file_path),
            ]
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=15,
                check=False,
            )
            duration_str = result.stdout.strip()
            if duration_str and duration_str != "N/A":
                dur = float(duration_str)
                if dur > 0:
                    return dur
        except Exception:
            pass

    # 2. Try ffprobe format duration
    try:
        cmd = [
            ffprobe_path,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(file_path),
        ]
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15,
            check=False,
        )
        duration_str = result.stdout.strip()
        if duration_str and duration_str != "N/A":
            dur = float(duration_str)
            if dur > 0:
                return dur
    except Exception:
        pass

    # 3. Fallback to ffmpeg -i parsing
    try:
        cmd = [ffmpeg_path, "-i", str(file_path)]
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15,
            check=False,
        )
        # Look for Duration: 00:01:23.45
        match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", result.stderr)
        if match:
            hours, minutes, seconds = match.groups()
            return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    except Exception as e:
        raise RuntimeError(f"Could not determine media duration for {file_path}: {e}")

    return 0.0


def sanitize_filename(name: str, max_length: int = 80) -> str:
    """Remove unsafe characters from video titles to make valid filesystem filenames."""
    # Strip emojis (4-byte unicode) for cross-platform compatibility
    sanitized = re.sub(r"[\U00010000-\U0010ffff]", "", name)
    # Replace full-width unicode pipe (U+FF5C) and common wide separators
    sanitized = sanitized.replace("\uff5c", "_").replace("｜", "_")
    # Replace invalid Windows/Linux filename characters with underscores
    sanitized = re.sub(r'[\\/*?:"<>|]', "_", sanitized)
    sanitized = re.sub(r"\s+", "_", sanitized)
    sanitized = re.sub(r"_+", "_", sanitized)
    sanitized = sanitized.strip(" ._")
    if not sanitized:
        sanitized = "video"
    return sanitized[:max_length]


def format_time(seconds: float) -> str:
    """Format seconds into a human-readable string: 'XX minutes XX seconds' or 'XX.X seconds'."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    remaining_seconds = int(seconds % 60)
    if minutes < 60:
        return f"{minutes}m {remaining_seconds}s"
    hours = int(minutes // 60)
    remaining_minutes = int(minutes % 60)
    return f"{hours}h {remaining_minutes}m {remaining_seconds}s"


def save_json(data: Any, file_path: Path) -> None:
    """Safely write JSON data with UTF-8 encoding and indented format."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    temp_file = file_path.with_suffix(".tmp")
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    temp_file.replace(file_path)


def load_json(file_path: Path) -> Optional[Any]:
    """Load JSON file if it exists, returning None otherwise."""
    if not file_path.is_file():
        return None
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


class StageTimer:
    """Context manager and tracker for profiling pipeline stages."""

    def __init__(self) -> None:
        self.timings: Dict[str, float] = {}
        self._current_stage: Optional[str] = None
        self._stage_start: float = 0.0
        self.total_start: float = time.time()
        self.total_duration: float = 0.0

    def start_stage(self, stage_name: str) -> None:
        """Begin timing a stage."""
        if self._current_stage:
            self.end_stage()
        self._current_stage = stage_name
        self._stage_start = time.time()

    def end_stage(self) -> float:
        """End timing the current stage and record its elapsed time."""
        if not self._current_stage:
            return 0.0
        elapsed = time.time() - self._stage_start
        self.timings[self._current_stage] = elapsed
        stage = self._current_stage
        self._current_stage = None
        return elapsed

    def finish(self) -> Dict[str, float]:
        """Finish overall timing and return all measurements."""
        if self._current_stage:
            self.end_stage()
        self.total_duration = time.time() - self.total_start
        self.timings["Total"] = self.total_duration
        return self.timings
