"""
Text-to-Speech (TTS) synthesis module using edge-tts.
Generates natural neural English speech per translated segment with async execution and caching.
"""

import asyncio
from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Callable, List, Optional

from src.config import DubbingConfig
from src.translator import TranslatedSegment


logger = logging.getLogger("dubbing")


@dataclass
class TTSSegment:
    id: int
    start: float
    end: float
    audio_path: Path
    text: str


class Synthesizer:
    """Manages neural speech synthesis for transcript segments."""

    def __init__(self, config: DubbingConfig):
        self.config = config

    def _sanitize_for_tts(self, text: str) -> str:
        """Sanitize text for English TTS by transliterating foreign scripts and stripping unspeakable characters."""
        from src.translator import transliterate_to_latin
        latin_text = transliterate_to_latin(text)
        cleaned = "".join(c for c in latin_text if ord(c) < 128)
        cleaned = cleaned.strip()
        return cleaned if cleaned else "..."

    def _generate_silent_audio(self, output_path: Path, duration: float) -> None:
        """Generate silent audio segment using FFmpeg as a reliable fallback."""
        import subprocess
        output_path.parent.mkdir(parents=True, exist_ok=True)
        dur = max(0.1, duration)
        cmd = [
            self.config.ffmpeg_path,
            "-y",
            "-f", "lavfi",
            "-i", "anullsrc=r=16000:cl=mono",
            "-t", f"{dur:.3f}",
            "-c:a", "libmp3lame",
            "-b:a", "64k",
            str(output_path),
        ]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except Exception as e:
            logger.error(f"Failed to generate silent fallback audio: {e}")
            raise RuntimeError(f"TTS failed and silent audio creation failed on segment: {e}")

    async def _synthesize_single_segment(
        self,
        text: str,
        output_file: Path,
        voice: str,
        rate: str = "+0%",
        pitch: str = "+0Hz",
    ) -> None:
        """Synthesize a single text string to an audio file using edge-tts."""
        import edge_tts

        communicate = edge_tts.Communicate(
            text=text,
            voice=voice,
            rate=rate,
            pitch=pitch,
        )
        await communicate.save(str(output_file))

    async def _synthesize_task(
        self,
        segment: TranslatedSegment,
        output_path: Path,
        sem: asyncio.Semaphore,
        on_done: Optional[Callable[[], None]] = None,
    ) -> TTSSegment:
        """Process an individual TTS segment with concurrency throttling and retry handling."""
        # Fast cache check before acquiring semaphore
        if output_path.is_file() and output_path.stat().st_size > 500 and not self.config.force and not self.config.fresh:
            if on_done:
                on_done()
            return TTSSegment(
                id=segment.id,
                start=segment.start,
                end=segment.end,
                audio_path=output_path,
                text=segment.translated_text,
            )

        text = segment.translated_text.strip()
        if not text:
            text = "..."  # Minimal pause fallback

        async with sem:
            # Re-check cache inside semaphore
            if output_path.is_file() and output_path.stat().st_size > 500 and not self.config.force and not self.config.fresh:
                if on_done:
                    on_done()
                return TTSSegment(
                    id=segment.id,
                    start=segment.start,
                    end=segment.end,
                    audio_path=output_path,
                    text=segment.translated_text,
                )

            last_err = None
            for attempt in range(3):
                try:
                    await self._synthesize_single_segment(
                        text=text,
                        output_file=output_path,
                        voice=self.config.tts_voice,
                        rate=self.config.tts_rate,
                        pitch=self.config.tts_pitch,
                    )
                    if output_path.is_file() and output_path.stat().st_size > 0:
                        break
                except Exception as e:
                    last_err = e
                    logger.debug(f"TTS retry {attempt + 1}/3 for segment {segment.id}: {e}")
                    await asyncio.sleep(0.5 * (attempt + 1))

            # If Edge-TTS failed, try transliterated / sanitized text
            if not output_path.is_file() or output_path.stat().st_size == 0:
                clean_text = self._sanitize_for_tts(text)
                if clean_text and clean_text != text:
                    try:
                        logger.warning(f"Retrying segment {segment.id} with sanitized text: '{clean_text}'")
                        await self._synthesize_single_segment(
                            text=clean_text,
                            output_file=output_path,
                            voice=self.config.tts_voice,
                            rate=self.config.tts_rate,
                            pitch=self.config.tts_pitch,
                        )
                    except Exception as e:
                        last_err = e
                        logger.debug(f"Sanitized TTS retry failed: {e}")

            # If still failing, generate silent audio fallback to preserve timeline
            if not output_path.is_file() or output_path.stat().st_size == 0:
                duration = max(0.2, segment.end - segment.start)
                logger.warning(
                    f"TTS failed on segment {segment.id} ('{text[:30]}...'): {last_err}. "
                    f"Generating silent fallback audio ({duration:.2f}s) to preserve timeline."
                )
                self._generate_silent_audio(output_path, duration)

        if not output_path.is_file() or output_path.stat().st_size == 0:
            raise RuntimeError(f"TTS output missing or empty for segment {segment.id} at {output_path}")

        if on_done:
            on_done()

        return TTSSegment(
            id=segment.id,
            start=segment.start,
            end=segment.end,
            audio_path=output_path,
            text=segment.translated_text,
        )

    def synthesize_segment(
        self,
        segment: TranslatedSegment,
        output_dir: Path,
    ) -> TTSSegment:
        """
        Generate audio for a single segment synchronously.
        Reuses existing audio if already generated and non-empty.
        """
        import hashlib
        output_dir.mkdir(parents=True, exist_ok=True)
        text_hash = hashlib.sha256(segment.translated_text.strip().encode()).hexdigest()[:8]
        filename = f"segment_{segment.id:04d}_{text_hash}.mp3"
        output_path = output_dir / filename

        # Check cache
        if output_path.is_file() and output_path.stat().st_size > 500 and not self.config.force and not self.config.fresh:
            logger.debug(f"Using cached TTS audio: {filename}")
            return TTSSegment(
                id=segment.id,
                start=segment.start,
                end=segment.end,
                audio_path=output_path,
                text=segment.translated_text,
            )

        text = segment.translated_text.strip()
        if not text:
            text = "..."

        try:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            loop.run_until_complete(
                self._synthesize_single_segment(
                    text=text,
                    output_file=output_path,
                    voice=self.config.tts_voice,
                    rate=self.config.tts_rate,
                    pitch=self.config.tts_pitch,
                )
            )

            if not output_path.is_file() or output_path.stat().st_size == 0:
                clean_text = self._sanitize_for_tts(text)
                if clean_text and clean_text != text:
                    loop.run_until_complete(
                        self._synthesize_single_segment(
                            text=clean_text,
                            output_file=output_path,
                            voice=self.config.tts_voice,
                            rate=self.config.tts_rate,
                            pitch=self.config.tts_pitch,
                        )
                    )

            if not output_path.is_file() or output_path.stat().st_size == 0:
                duration = max(0.2, segment.end - segment.start)
                self._generate_silent_audio(output_path, duration)

        except Exception as e:
            duration = max(0.2, segment.end - segment.start)
            logger.warning(f"TTS exception on segment {segment.id}: {e}. Generating silent fallback audio.")
            self._generate_silent_audio(output_path, duration)

        if not output_path.is_file() or output_path.stat().st_size == 0:
            raise RuntimeError(f"TTS output missing or empty for segment {segment.id} at {output_path}")

        return TTSSegment(
            id=segment.id,
            start=segment.start,
            end=segment.end,
            audio_path=output_path,
            text=segment.translated_text,
        )

    async def _synthesize_all_concurrent(
        self,
        segments: List[TranslatedSegment],
        output_dir: Path,
        concurrency: int = 8,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> List[TTSSegment]:
        """Asynchronously process all segments concurrently with throttled concurrency."""
        import hashlib
        sem = asyncio.Semaphore(concurrency)
        total = len(segments)
        completed = 0

        def on_done():
            nonlocal completed
            completed += 1
            if progress_callback:
                progress_callback(completed, total)

        tasks = []
        for seg in segments:
            text_hash = hashlib.sha256(seg.translated_text.strip().encode()).hexdigest()[:8]
            filename = f"segment_{seg.id:04d}_{text_hash}.mp3"
            out_path = output_dir / filename
            tasks.append(self._synthesize_task(seg, out_path, sem, on_done))

        raw_results = await asyncio.gather(*tasks)
        # Guarantee strict chronological sorting by start timestamp
        return sorted(raw_results, key=lambda s: (s.start, s.end))

    def synthesize_all(
        self,
        segments: List[TranslatedSegment],
        output_dir: Path,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        concurrency: int = 8,
    ) -> List[TTSSegment]:
        """
        Synthesize audio for all segments with concurrent async execution.
        Supports caching and periodic progress reporting.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        if not segments:
            return []

        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(
            self._synthesize_all_concurrent(
                segments=segments,
                output_dir=output_dir,
                concurrency=concurrency,
                progress_callback=progress_callback,
            )
        )
