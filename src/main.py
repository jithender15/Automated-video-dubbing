"""
CLI entry point for the Automated Video Dubbing System.
Usage:
    python src/main.py "https://www.youtube.com/watch?v=VIDEO_ID"
"""

import argparse
import sys
from pathlib import Path

# Ensure UTF-8 output encoding across Windows consoles
if sys.platform == "win32":
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if sys.stderr and hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Add project root to sys.path so src imports resolve cleanly
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.config import DubbingConfig
from src.pipeline import DubbingPipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Automated Video Dubbing System: Translate and dub foreign YouTube videos into English."
    )
    parser.add_argument(
        "url",
        type=str,
        help="YouTube video URL (e.g. 'https://www.youtube.com/watch?v=VIDEO_ID')",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Whisper model size: tiny, base, small, medium, large (default: base)",
    )
    parser.add_argument(
        "--voice",
        type=str,
        default=None,
        help="Microsoft Edge TTS voice name (default: en-US-AriaNeural)",
    )
    parser.add_argument(
        "--backend",
        type=str,
        default=None,
        help="Translation backend: google, mock (default: google)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Directory to save final dubbed videos (default: outputs/)",
    )
    parser.add_argument(
        "--temp-dir",
        type=str,
        default=None,
        help="Directory to store intermediate artifacts (default: temp/)",
    )
    parser.add_argument(
        "--ffmpeg-path",
        type=str,
        default=None,
        help="Path to ffmpeg executable if not in PATH",
    )
    parser.add_argument(
        "--benchmark",
        action="store_true",
        help="Measure and report detailed stage processing time",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-processing of all stages, ignoring cached files",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Clean test mode: purge all caches and create isolated temporary job directory",
    )
    parser.add_argument(
        "--cleanup-intermediates",
        action="store_true",
        help="Remove temporary segment audio files after timeline assembly to save disk space",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    # Initialize configuration
    config = DubbingConfig()
    if args.model:
        config.whisper_model = args.model
    if args.voice:
        config.tts_voice = args.voice
    if args.backend:
        config.translation_backend = args.backend
    if args.output_dir:
        config.output_dir = Path(args.output_dir)
    if args.temp_dir:
        config.temp_dir = Path(args.temp_dir)
    if args.ffmpeg_path:
        config.ffmpeg_path = args.ffmpeg_path
    if args.benchmark:
        config.benchmark = True
    if args.force:
        config.force = True
    if args.fresh:
        config.fresh = True
    if args.cleanup_intermediates:
        config.cleanup_intermediates = True

    try:
        pipeline = DubbingPipeline(config)
        pipeline.run(args.url)
        return 0

    except KeyboardInterrupt:
        print("\n[!] Process interrupted by user.")
        return 130
    except Exception as e:
        print(f"\nERROR: {str(e)}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
