"""
Speech Transcription and Language Detection module using OpenAI Whisper.
Extracts segment-level timestamps and source language.
"""

from dataclasses import asdict, dataclass
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.config import DubbingConfig
from src.utils import load_json, save_json


logger = logging.getLogger("dubbing")


@dataclass
class TranscriptSegment:
    id: int
    start: float
    end: float
    text: str


@dataclass
class TranscriptionResult:
    language: str
    segments: List[TranscriptSegment]
    full_text: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "language": self.language,
            "segments": [asdict(seg) for seg in self.segments],
            "full_text": self.full_text,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TranscriptionResult":
        segments = [
            TranscriptSegment(
                id=seg.get("id", i),
                start=float(seg.get("start", 0.0)),
                end=float(seg.get("end", 0.0)),
                text=seg.get("text", "").strip(),
            )
            for i, seg in enumerate(data.get("segments", []))
        ]
        return cls(
            language=data.get("language", "unknown"),
            segments=segments,
            full_text=data.get("full_text", ""),
        )


class Transcriber:
    """Manages Whisper model loading and speech transcription."""

    _cached_model = None
    _cached_model_name = None

    def __init__(self, config: DubbingConfig):
        self.config = config

    @classmethod
    def unload_model(cls) -> None:
        """Explicitly unload Whisper model from memory and free CUDA/system RAM."""
        if cls._cached_model is not None:
            logger.debug(f"Unloading Whisper model '{cls._cached_model_name}' to free memory...")
            del cls._cached_model
            cls._cached_model = None
            cls._cached_model_name = None
            try:
                import gc
                gc.collect()
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass
            logger.info("Whisper model unloaded from memory.")

    def _get_model(self):
        """Load Whisper model once and keep in memory for subsequent operations."""
        model_name = self.config.whisper_model
        if Transcriber._cached_model is not None and Transcriber._cached_model_name == model_name:
            return Transcriber._cached_model

        try:
            import whisper
        except ImportError:
            raise RuntimeError(
                "openai-whisper is not installed. Please install it using: pip install openai-whisper"
            )

        device = self.config.whisper_device
        logger.info(f"Loading Whisper model '{model_name}'...")
        try:
            model = whisper.load_model(model_name, device=device)
            Transcriber._cached_model = model
            Transcriber._cached_model_name = model_name
            return model
        except Exception as e:
            raise RuntimeError(f"Failed to load Whisper model '{model_name}': {str(e)}")

    def transcribe(
        self,
        audio_path: Path,
        cache_path: Optional[Path] = None,
        task: Optional[str] = None,
    ) -> TranscriptionResult:
        """
        Transcribe or translate the audio file using Whisper.
        Reuses cached transcript if available and valid unless force=True.
        """
        if not audio_path.is_file():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        # Check cache
        if cache_path and cache_path.is_file() and not self.config.force and not self.config.fresh:
            cached_data = load_json(cache_path)
            if cached_data and "segments" in cached_data:
                logger.info("Using cached transcription data.")
                return TranscriptionResult.from_dict(cached_data)

        model = self._get_model()
        actual_task = task or getattr(self.config, "whisper_task", "translate")

        logger.debug(f"Running Whisper ({actual_task}) on audio file: {audio_path}")
        try:
            # Transcribe with automatic language detection and segment timestamps
            result = model.transcribe(
                str(audio_path),
                verbose=False,
                task=actual_task,
                fp16=False,  # CPU compatibility
            )
        except Exception as e:
            raise RuntimeError(f"Whisper processing failed: {str(e)}")

        detected_language = result.get("language", "unknown")
        raw_segments = result.get("segments", [])

        segments: List[TranscriptSegment] = []
        full_text_parts = []

        for idx, seg in enumerate(raw_segments):
            text = seg.get("text", "").strip()
            # Omit empty or noise-only segments
            if not text:
                continue
            start = round(float(seg.get("start", 0.0)), 3)
            end = round(float(seg.get("end", 0.0)), 3)
            if end <= start:
                end = start + 0.5  # Ensure minimum non-zero duration

            segments.append(
                TranscriptSegment(
                    id=idx,
                    start=start,
                    end=end,
                    text=text,
                )
            )
            full_text_parts.append(text)

        # Enforce strict chronological ordering and sequential IDs (Rule #6)
        segments.sort(key=lambda s: (s.start, s.end))
        for i, s in enumerate(segments):
            s.id = i

        if segments:
            logger.info(
                f"Whisper {actual_task} complete: {len(segments)} segments, "
                f"first: {segments[0].start:.2f}s, last: {segments[-1].end:.2f}s, "
                f"language: {detected_language}"
            )

        transcription_result = TranscriptionResult(
            language=detected_language,
            segments=segments,
            full_text=" ".join(full_text_parts),
        )

        if cache_path:
            save_json(transcription_result.to_dict(), cache_path)
            logger.debug(f"Saved transcript to {cache_path}")

        return transcription_result
