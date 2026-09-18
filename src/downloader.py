"""
YouTube Downloader module using yt-dlp.
Handles URL validation, download progress reporting, sanitization, and error handling.
"""

from dataclasses import dataclass
import logging
from pathlib import Path
import re
import shutil
from typing import Callable, Optional

from src.config import DubbingConfig
from src.utils import get_media_duration


logger = logging.getLogger("dubbing")

YOUTUBE_URL_REGEX = re.compile(
    r"^(https?://)?(www\.)?(youtube\.com/(watch\?v=|shorts/|embed/)|youtu\.be/)([\w-]{11})",
    re.IGNORECASE,
)


@dataclass
class DownloadResult:
    video_path: Path
    video_id: str
    title: str
    duration: float


def validate_youtube_url(url: str) -> bool:
    """Validate if the given string is a valid YouTube video URL."""
    if not url or not isinstance(url, str):
        return False
    return bool(YOUTUBE_URL_REGEX.search(url.strip()))


def extract_video_id(url: str) -> Optional[str]:
    """Extract the 11-character YouTube video ID from a URL."""
    match = YOUTUBE_URL_REGEX.search(url.strip())
    if match:
        return match.group(5)
    return None


class Downloader:
    """Encapsulates video downloading with yt-dlp."""

    def __init__(self, config: DubbingConfig):
        self.config = config

    def download(
        self,
        url: str,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> DownloadResult:
        """
        Download a YouTube video given its URL.
        Reuses existing file if already downloaded and valid unless force=True.
        """
        clean_url = url.strip()
        if not validate_youtube_url(clean_url):
            raise ValueError(
                f"Invalid YouTube URL: '{url}'. Expected format: https://www.youtube.com/watch?v=VIDEO_ID or https://youtu.be/VIDEO_ID"
            )

        video_id = extract_video_id(clean_url) or "unknown"
        self.config.download_dir.mkdir(parents=True, exist_ok=True)

        # Check if already downloaded
        existing_matches = list(self.config.download_dir.glob(f"*{video_id}*.mp4")) + \
                           list(self.config.download_dir.glob(f"*{video_id}*.mkv")) + \
                           list(self.config.download_dir.glob(f"*{video_id}*.webm"))
        if existing_matches and not self.config.force:
            existing_file = existing_matches[0]
            if existing_file.stat().st_size > 0:
                logger.info(f"Using cached download: {existing_file.name}")
                exact_dur = get_media_duration(
                    existing_file,
                    self.config.ffprobe_path,
                    self.config.ffmpeg_path,
                    stream_type="v",
                )
                return DownloadResult(
                    video_path=existing_file,
                    video_id=video_id,
                    title=existing_file.stem,
                    duration=exact_dur,
                )

        try:
            import yt_dlp
        except ImportError:
            raise RuntimeError(
                "yt-dlp is not installed. Please install it using: pip install yt-dlp"
            )

        # Custom progress hook for clean terminal reporting
        def ytdl_progress_hook(d: dict) -> None:
            if d.get("status") == "downloading":
                total_bytes = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                downloaded_bytes = d.get("downloaded_bytes") or 0
                if total_bytes > 0:
                    percent = (downloaded_bytes / total_bytes) * 100
                    if progress_callback:
                        progress_callback(f"Downloading: {percent:.1f}%")

        outtmpl = str(self.config.download_dir / f"%(title)s_{video_id}.%(ext)s")

        ffmpeg_dir = str(Path(self.config.ffmpeg_path).parent) if Path(self.config.ffmpeg_path).is_file() else None
        node_bin = shutil.which("node")

        ydl_opts = {
            "format": "bestvideo[vcodec^=avc1][ext=mp4]+bestaudio[ext=m4a]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "outtmpl": outtmpl,
            "quiet": True,
            "no_warnings": True,
            "progress_hooks": [ytdl_progress_hook],
            "merge_output_format": "mp4",
            "overwrites": self.config.force,
        }
        if ffmpeg_dir:
            ydl_opts["ffmpeg_location"] = ffmpeg_dir
        if node_bin:
            ydl_opts["js_runtimes"] = {"node": {"path": node_bin}}

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(clean_url, download=True)
                title = info.get("title", f"video_{video_id}")
                duration = float(info.get("duration", 0.0) or 0.0)
                downloaded_filename = ydl.prepare_filename(info)

                # Ensure output is mp4 if merged
                expected_mp4 = Path(downloaded_filename).with_suffix(".mp4")
                if expected_mp4.is_file():
                    target_path = expected_mp4
                else:
                    target_path = Path(downloaded_filename)

                if not target_path.is_file() or target_path.stat().st_size == 0:
                    # Search directory for file containing video_id
                    found = list(self.config.download_dir.glob(f"*{video_id}*"))
                    if found:
                        target_path = found[0]
                    else:
                        raise RuntimeError(f"Download finished but file not found at {target_path}")

                exact_dur = get_media_duration(
                    target_path,
                    self.config.ffprobe_path,
                    self.config.ffmpeg_path,
                    stream_type="v",
                )
                if exact_dur <= 0:
                    exact_dur = duration

                return DownloadResult(
                    video_path=target_path,
                    video_id=video_id,
                    title=title,
                    duration=exact_dur,
                )

        except yt_dlp.utils.DownloadError as e:
            error_msg = str(e)
            if "Video unavailable" in error_msg:
                raise RuntimeError(f"The YouTube video is unavailable or has been removed: {clean_url}")
            elif "Private video" in error_msg:
                raise RuntimeError(f"The YouTube video is private: {clean_url}")
            elif "Sign in to confirm your age" in error_msg:
                raise RuntimeError("Age-restricted video cannot be downloaded without authentication.")
            else:
                raise RuntimeError(f"YouTube download failed: {error_msg}")
        except Exception as e:
            raise RuntimeError(f"Unexpected error during download: {str(e)}")
