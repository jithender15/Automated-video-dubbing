"""
Video processing and muxing module using FFmpeg.
Combines original video stream with newly dubbed English audio track,
avoiding video re-encoding (-c:v copy) whenever possible while ensuring
universal playback compatibility and zero video truncation.
"""

import json
import logging
from pathlib import Path
import subprocess

from src.config import DubbingConfig
from src.utils import get_media_duration


logger = logging.getLogger("dubbing")


def get_video_codec(video_path: Path, ffprobe_path: str) -> str:
    """Extract video stream codec name via ffprobe."""
    cmd = [
        ffprobe_path,
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=codec_name",
        "-of", "json",
        str(video_path),
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(res.stdout)
        streams = data.get("streams", [])
        if streams:
            return streams[0].get("codec_name", "").lower()
    except Exception:
        pass
    return "unknown"


class VideoProcessor:
    """Muxes original video visual stream with dubbed audio."""

    def __init__(self, config: DubbingConfig):
        self.config = config

    def create_dubbed_video(
        self,
        original_video_path: Path,
        dubbed_audio_path: Path,
        output_video_path: Path,
    ) -> Path:
        """
        Mux the original video stream with the dubbed audio track.
        Guarantees:
        - The video is never cut short (no -shortest truncation)
        - Audio is automatically padded with silence if shorter than video
        - Audio is capped at exact video duration to prevent overruns
        - Universal MP4 playback compatibility (H.264/AAC)
        """
        if not original_video_path.is_file():
            raise FileNotFoundError(f"Original video not found: {original_video_path}")
        if not dubbed_audio_path.is_file():
            raise FileNotFoundError(f"Dubbed audio not found: {dubbed_audio_path}")

        output_video_path.parent.mkdir(parents=True, exist_ok=True)

        if output_video_path.is_file() and output_video_path.stat().st_size > 1024 and not self.config.force and not self.config.fresh:
            logger.info(f"Using cached dubbed video: {output_video_path.name}")
            return output_video_path

        # Determine exact video stream duration
        v_dur = get_media_duration(
            original_video_path,
            self.config.ffprobe_path,
            self.config.ffmpeg_path,
            stream_type="v",
        )
        if v_dur <= 0:
            v_dur = get_media_duration(
                original_video_path, self.config.ffprobe_path, self.config.ffmpeg_path
            )

        codec = get_video_codec(original_video_path, self.config.ffprobe_path)
        is_standard_h264 = codec in ("h264", "avc1", "hevc", "h265")
        logger.debug(f"Detected video codec: {codec} (standard MP4 compatibility: {is_standard_h264})")

        # Audio padding filter: ensures audio track never ends before video stream
        audio_filter = f"apad=whole_dur={v_dur:.3f}" if v_dur > 0 else "anull"

        # Attempt 1: Fast stream copy without re-encoding video if codec is standard MP4
        if is_standard_h264:
            fast_cmd = [
                self.config.ffmpeg_path,
                "-y",
                "-i", str(original_video_path),
                "-i", str(dubbed_audio_path),
                "-filter_complex", f"[1:a]{audio_filter}[aout]",
                "-map", "0:v:0",
                "-map", "[aout]",
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "192k",
                "-t", f"{v_dur:.3f}" if v_dur > 0 else "999999",
                "-movflags", "+faststart",
                str(output_video_path),
            ]

            logger.debug(f"Attempting fast video mux: {' '.join(fast_cmd)}")
            res = subprocess.run(
                fast_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            if res.returncode == 0 and output_video_path.is_file() and output_video_path.stat().st_size > 0:
                duration = get_media_duration(
                    output_video_path, self.config.ffprobe_path, self.config.ffmpeg_path
                )
                logger.debug(f"Dubbed video successfully created via stream copy: {duration:.2f}s")
                return output_video_path

            logger.warning(
                f"Fast video copy (-c:v copy) failed or non-standard. Falling back to universal libx264 transcode: {res.stderr.strip()}"
            )

        # Attempt 2: Re-encode video stream using libx264 for 100% universal compatibility
        transcode_cmd = [
            self.config.ffmpeg_path,
            "-y",
            "-i", str(original_video_path),
            "-i", str(dubbed_audio_path),
            "-filter_complex", f"[1:a]{audio_filter}[aout]",
            "-map", "0:v:0",
            "-map", "[aout]",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "20",
            "-c:a", "aac",
            "-b:a", "192k",
            "-t", f"{v_dur:.3f}" if v_dur > 0 else "999999",
            "-movflags", "+faststart",
            str(output_video_path),
        ]
        res_fallback = subprocess.run(
            transcode_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if res_fallback.returncode != 0:
            raise RuntimeError(
                f"FFmpeg video muxing failed completely:\n{res_fallback.stderr.strip()}"
            )

        if not output_video_path.is_file() or output_video_path.stat().st_size == 0:
            raise RuntimeError(f"Output video was not created at {output_video_path}")

        duration = get_media_duration(
            output_video_path, self.config.ffprobe_path, self.config.ffmpeg_path
        )
        logger.debug(f"Dubbed video successfully created: {duration:.2f}s ({output_video_path})")

        return output_video_path
