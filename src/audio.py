"""
Audio extraction and conversion utilities using FFmpeg.
Converts input video into 16kHz mono WAV suitable for Whisper transcription.
"""

import logging
from pathlib import Path
import subprocess

from src.config import DubbingConfig


logger = logging.getLogger("dubbing")


class AudioExtractor:
    """Extracts and formats audio from video files for Whisper transcription."""

    def __init__(self, config: DubbingConfig):
        self.config = config

    def extract_audio(self, video_path: Path, output_wav_path: Path) -> Path:
        """
        Extract mono 16kHz WAV audio from a video file using FFmpeg.
        Reuses existing WAV file if valid unless force is enabled.
        """
        if not video_path.is_file():
            raise FileNotFoundError(f"Input video not found: {video_path}")

        output_wav_path.parent.mkdir(parents=True, exist_ok=True)

        if output_wav_path.is_file() and output_wav_path.stat().st_size > 1024 and not self.config.force and not self.config.fresh:
            logger.info(f"Using cached extracted audio: {output_wav_path.name}")
            return output_wav_path

        cmd = [
            self.config.ffmpeg_path,
            "-y",                                   # Overwrite output file
            "-i", str(video_path),                  # Input video
            "-vn",                                  # Disable video stream
            "-af", "aresample=async=1000",          # Strict audio-video timestamp synchronization
            "-acodec", "pcm_s16le",                 # 16-bit PCM WAV
            "-ac", str(self.config.audio_channels), # 1 channel (mono)
            "-ar", str(self.config.sample_rate),    # 16000 Hz sample rate
            str(output_wav_path),
        ]

        logger.debug(f"Running audio extraction command: {' '.join(cmd)}")
        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"FFmpeg audio extraction failed (exit code {result.returncode}):\n{result.stderr.strip()}"
                )
        except FileNotFoundError:
            raise RuntimeError(
                f"FFmpeg executable not found at '{self.config.ffmpeg_path}'. Ensure FFmpeg is installed and in PATH."
            )
        except Exception as e:
            raise RuntimeError(f"Failed to extract audio from video: {str(e)}")

        if not output_wav_path.is_file() or output_wav_path.stat().st_size == 0:
            raise RuntimeError(f"Audio extraction produced an empty or missing file at {output_wav_path}")

        return output_wav_path
