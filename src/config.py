"""
Configuration management for the Automated Video Dubbing System.
Loads defaults and allows overrides via environment variables or CLI options.
"""

from dataclasses import dataclass, field
import os
from pathlib import Path
import shutil
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Base project directory is the parent directory of 'src'
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def get_default_ffmpeg_path() -> str:
    """Find FFmpeg binary from PATH or common installation directories."""
    # 1. Check environment variable override
    env_path = os.environ.get("FFMPEG_PATH")
    if env_path and Path(env_path).is_file():
        return env_path

    # 2. Check system PATH
    system_path = shutil.which("ffmpeg")
    if system_path:
        return system_path

    # 3. Check common Windows installation locations
    candidate_paths = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages",
        Path("C:/Program Files/ffmpeg/bin/ffmpeg.exe"),
        Path("C:/ffmpeg/bin/ffmpeg.exe"),
        Path(os.environ.get("USERPROFILE", "")) / "ffmpeg" / "bin" / "ffmpeg.exe",
        PROJECT_ROOT / "bin" / "ffmpeg.exe",
    ]

    for candidate in candidate_paths:
        if candidate.is_file():
            return str(candidate)
        if candidate.is_dir():
            # Search winget package directory recursively for ffmpeg.exe
            found = list(candidate.glob("**/ffmpeg.exe"))
            if found:
                return str(found[0])

    return "ffmpeg"  # Fallback to standard command name


def get_default_ffprobe_path() -> str:
    """Find FFprobe binary from PATH or common installation directories."""
    env_path = os.environ.get("FFPROBE_PATH")
    if env_path and Path(env_path).is_file():
        return env_path

    system_path = shutil.which("ffprobe")
    if system_path:
        return system_path

    candidate_paths = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages",
        Path("C:/Program Files/ffmpeg/bin/ffprobe.exe"),
        Path("C:/ffmpeg/bin/ffprobe.exe"),
        Path(os.environ.get("USERPROFILE", "")) / "ffmpeg" / "bin" / "ffprobe.exe",
        PROJECT_ROOT / "bin" / "ffprobe.exe",
    ]

    for candidate in candidate_paths:
        if candidate.is_file():
            return str(candidate)
        if candidate.is_dir():
            found = list(candidate.glob("**/ffprobe.exe"))
            if found:
                return str(found[0])

    return "ffprobe"


@dataclass
class DubbingConfig:
    """Configuration settings for video dubbing pipeline."""

    # Directories
    project_root: Path = field(default_factory=lambda: PROJECT_ROOT)
    download_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "downloads")
    temp_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "temp")
    output_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "outputs")
    log_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "logs")

    # Transcription (Whisper)
    whisper_model: str = field(
        default_factory=lambda: os.environ.get("WHISPER_MODEL", "base")
    )
    whisper_device: Optional[str] = field(
        default_factory=lambda: os.environ.get("WHISPER_DEVICE", None)
    )
    whisper_task: str = field(
        default_factory=lambda: os.environ.get("WHISPER_TASK", "translate")
    )

    # Translation
    translation_backend: str = field(
        default_factory=lambda: os.environ.get("TRANSLATION_BACKEND", "google")
    )
    target_language: str = "en"

    # Text to Speech (edge-tts)
    tts_voice: str = field(
        default_factory=lambda: os.environ.get("TTS_VOICE", "en-US-AriaNeural")
    )
    tts_rate: str = "+0%"
    tts_pitch: str = "+0Hz"

    # Audio & Synchronization parameters
    sample_rate: int = 16000
    audio_channels: int = 1
    min_tempo: float = 0.85  # Don't slow speech down past 0.85x
    max_tempo: float = 1.25  # Strict normal human speaking speed limit (prevents rushed robotic speech)

    # FFmpeg paths
    ffmpeg_path: str = field(default_factory=get_default_ffmpeg_path)
    ffprobe_path: str = field(default_factory=get_default_ffprobe_path)

    # Pipeline execution controls
    force: bool = False
    fresh: bool = False
    benchmark: bool = False
    cleanup_intermediates: bool = False

    def __post_init__(self) -> None:
        """Ensure FFmpeg bin directory is on os.environ['PATH']."""
        if self.ffmpeg_path and Path(self.ffmpeg_path).is_file():
            ffmpeg_dir = str(Path(self.ffmpeg_path).parent)
            current_path = os.environ.get("PATH", "")
            if ffmpeg_dir not in current_path:
                os.environ["PATH"] = f"{ffmpeg_dir}{os.pathsep}{current_path}"

    def ensure_directories(self) -> None:
        """Create all necessary runtime directories if they don't exist."""
        for path in [
            self.download_dir,
            self.temp_dir,
            self.output_dir,
            self.log_dir,
        ]:
            path.mkdir(parents=True, exist_ok=True)

    def get_job_temp_dir(self, video_id: str, url: str = "") -> Path:
        """
        Get an isolated temporary directory for a specific video job.
        Creates standard subdirectories: source, audio, transcript, translation, tts, sync, final, logs.
        """
        import hashlib
        url_hash = hashlib.sha256((url or video_id).strip().encode()).hexdigest()[:8]
        job_dir = self.temp_dir / "jobs" / f"{video_id}_{url_hash}"
        job_dir.mkdir(parents=True, exist_ok=True)

        for sub in ["source", "audio", "transcript", "translation", "tts", "sync", "final", "logs"]:
            (job_dir / sub).mkdir(parents=True, exist_ok=True)

        return job_dir
