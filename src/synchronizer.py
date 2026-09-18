"""
Audio Synchronization and Timeline Assembly module.
Aligns translated TTS speech segments to original Whisper timestamps using:
- Absolute sample-accurate timeline placement (zero cumulative drift)
- Energy-based silence trimming (eliminates edge-tts dead air)
- Intelligent gap utilization (uses natural pauses before speeding up speech)
- Intelligibility-preserving tempo scaling with pitch preservation (atempo)
- Click-free boundary crossfading and smooth overlap management
- Automatic sample-rate verification and on-the-fly resampling
"""

from dataclasses import dataclass
import logging
from pathlib import Path
import subprocess
from typing import List, Optional
import wave

try:
    import numpy as np
except ImportError:
    np = None

from src.config import DubbingConfig
from src.synthesizer import TTSSegment
from src.utils import get_media_duration


logger = logging.getLogger("dubbing")


@dataclass
class SynchronizedSegment:
    id: int
    start: float
    end: float
    original_duration: float
    tts_duration: float
    adjusted_duration: float
    tempo_factor: float
    audio_path: Path


class Synchronizer:
    """Synchronizes individual TTS audio segments to original video timeline."""

    def __init__(self, config: DubbingConfig):
        self.config = config

    def calculate_tempo(self, tts_duration: float, target_duration: float) -> float:
        """
        Calculate the required audio tempo adjustment factor.
        Clamps the factor within [min_tempo, max_tempo] to maintain natural intelligibility.
        """
        if target_duration <= 0 or tts_duration <= 0:
            return 1.0

        raw_ratio = tts_duration / target_duration
        if raw_ratio > 1.03:
            return min(raw_ratio, self.config.max_tempo)
        elif raw_ratio < 0.70:
            return max(raw_ratio, self.config.min_tempo)
        return 1.0

    def _trim_silence_numpy(
        self, samples: "np.ndarray", sample_rate: int, threshold: int = 400
    ) -> "np.ndarray":
        """
        Trim leading and trailing silence from 16-bit PCM audio samples.
        Preserves small padding windows (25ms start, 35ms end) so initial attacks
        and consonant decays are never clipped.
        """
        non_silent = np.where(np.abs(samples) > threshold)[0]
        if len(non_silent) == 0:
            return samples

        pad_start = int(0.025 * sample_rate)
        pad_end = int(0.035 * sample_rate)

        start_idx = max(0, non_silent[0] - pad_start)
        end_idx = min(len(samples), non_silent[-1] + pad_end)

        trimmed = samples[start_idx:end_idx].copy()

        # Apply gentle 15ms fade-in and 20ms fade-out to prevent clicks
        fade_in_len = min(int(0.015 * sample_rate), len(trimmed))
        if fade_in_len > 1:
            fade_in = np.linspace(0.0, 1.0, fade_in_len, dtype=np.float32)
            trimmed[:fade_in_len] = (trimmed[:fade_in_len] * fade_in).astype(np.int16)

        fade_out_len = min(int(0.020 * sample_rate), len(trimmed))
        if fade_out_len > 1:
            fade_out = np.linspace(1.0, 0.0, fade_out_len, dtype=np.float32)
            trimmed[-fade_out_len:] = (trimmed[-fade_out_len:] * fade_out).astype(np.int16)

        return trimmed

    def adjust_segment_tempo(
        self,
        segment: TTSSegment,
        output_wav: Path,
        next_start: Optional[float] = None,
        total_duration: Optional[float] = None,
    ) -> SynchronizedSegment:
        """
        Prepare segment audio:
        1. Convert raw TTS MP3 to 16kHz mono PCM WAV.
        2. Trim artificial leading/trailing silence to measure pure speech duration.
        3. Evaluate available window (utilizing natural gaps before next segment).
        4. Apply smart tempo adjustment if pure speech exceeds available window.
        """
        output_wav.parent.mkdir(parents=True, exist_ok=True)
        sample_rate = self.config.sample_rate
        orig_duration = max(0.1, segment.end - segment.start)

        # Check cache: reuse already-adjusted segment audio if valid
        if output_wav.is_file() and output_wav.stat().st_size > 500 and not self.config.force and not self.config.fresh:
            adj_duration = get_media_duration(
                output_wav, self.config.ffprobe_path, self.config.ffmpeg_path
            )
            return SynchronizedSegment(
                id=segment.id,
                start=segment.start,
                end=segment.end,
                original_duration=orig_duration,
                tts_duration=orig_duration,
                adjusted_duration=adj_duration,
                tempo_factor=1.0,
                audio_path=output_wav,
            )

        # Raw intermediate WAV converted from TTS output
        raw_temp_wav = output_wav.with_suffix(".raw.wav")

        # Step 1: Decode TTS audio to standard 16kHz mono PCM WAV
        decode_cmd = [
            self.config.ffmpeg_path,
            "-y",
            "-i", str(segment.audio_path),
            "-acodec", "pcm_s16le",
            "-ac", str(self.config.audio_channels),
            "-ar", str(sample_rate),
            str(raw_temp_wav),
        ]
        res_decode = subprocess.run(
            decode_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if res_decode.returncode != 0 or not raw_temp_wav.is_file():
            raise RuntimeError(
                f"Failed to decode TTS segment {segment.id} audio: {res_decode.stderr.strip()}"
            )

        # Step 2: Read raw samples and perform energy-based silence trimming
        raw_samples = None
        if np is not None:
            try:
                with wave.open(str(raw_temp_wav), "rb") as wf:
                    frames = wf.readframes(wf.getnframes())
                    raw_samples = np.frombuffer(frames, dtype=np.int16)
            except Exception as e:
                logger.warning(f"Failed to read WAV samples for segment {segment.id}: {e}")

        initial_duration = (
            len(raw_samples) / sample_rate if raw_samples is not None
            else get_media_duration(raw_temp_wav, self.config.ffprobe_path, self.config.ffmpeg_path)
        )

        if np is not None and raw_samples is not None and len(raw_samples) > 0:
            trimmed_samples = self._trim_silence_numpy(raw_samples, sample_rate)
            spoken_duration = len(trimmed_samples) / sample_rate
            # Write trimmed audio back to raw_temp_wav
            with wave.open(str(raw_temp_wav), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(trimmed_samples.tobytes())
        else:
            trimmed_samples = None
            spoken_duration = initial_duration

        # Step 3: Determine available time window including natural gaps
        if next_start is not None and next_start > segment.start:
            available_time = next_start - segment.start
            # Leave at least 80ms natural pause before the next segment starts
            safe_limit = max(orig_duration, available_time - 0.08)
        elif total_duration is not None and total_duration > segment.start:
            available_time = total_duration - segment.start
            safe_limit = max(orig_duration, available_time - 0.08)
        else:
            safe_limit = orig_duration

        # Step 4: Calculate optimal tempo
        # If pure speech fits within available window, keep natural 1.0x tempo!
        if spoken_duration <= safe_limit:
            tempo = 1.0
        else:
            # Need to speed up to fit before next segment begins
            tempo = self.calculate_tempo(spoken_duration, safe_limit)

        # Step 5: Apply tempo adjustment via FFmpeg atempo if needed
        try:
            if abs(tempo - 1.0) > 0.02:
                # Apply high-quality WSOLA atempo scaling
                tempo_cmd = [
                    self.config.ffmpeg_path,
                    "-y",
                    "-i", str(raw_temp_wav),
                    "-filter:a", f"atempo={tempo:.3f},afade=t=in:ss=0:d=0.015,afade=t=out:st={spoken_duration/tempo - 0.02:.3f}:d=0.02",
                    "-acodec", "pcm_s16le",
                    "-ac", str(self.config.audio_channels),
                    "-ar", str(sample_rate),
                    str(output_wav),
                ]
                res_tempo = subprocess.run(
                    tempo_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=False,
                )
                if res_tempo.returncode != 0:
                    # Fallback without fade parameters if audio is short
                    fallback_tempo_cmd = [
                        self.config.ffmpeg_path,
                        "-y",
                        "-i", str(raw_temp_wav),
                        "-filter:a", f"atempo={tempo:.3f}",
                        "-acodec", "pcm_s16le",
                        "-ac", str(self.config.audio_channels),
                        "-ar", str(sample_rate),
                        str(output_wav),
                    ]
                    subprocess.run(fallback_tempo_cmd, check=True)
            else:
                # No tempo adjustment needed: replace raw_temp_wav to output_wav
                if output_wav.is_file():
                    output_wav.unlink()
                raw_temp_wav.replace(output_wav)

        except Exception as e:
            logger.warning(f"Tempo adjustment failed for segment {segment.id}, using raw WAV: {e}")
            if raw_temp_wav.is_file():
                if output_wav.is_file():
                    output_wav.unlink()
                raw_temp_wav.replace(output_wav)
        finally:
            if raw_temp_wav.is_file():
                try:
                    raw_temp_wav.unlink()
                except OSError:
                    pass

        adj_duration = get_media_duration(
            output_wav, self.config.ffprobe_path, self.config.ffmpeg_path
        )

        return SynchronizedSegment(
            id=segment.id,
            start=segment.start,
            end=segment.end,
            original_duration=orig_duration,
            tts_duration=initial_duration,
            adjusted_duration=adj_duration,
            tempo_factor=tempo,
            audio_path=output_wav,
        )

    def _ensure_correct_wav_format(self, audio_path: Path, sample_rate: int) -> bytes:
        """
        Verify that a WAV file is 16kHz mono 16-bit PCM.
        If not, automatically resample and re-encode using FFmpeg on the fly.
        """
        try:
            with wave.open(str(audio_path), "rb") as wf:
                n_channels = wf.getnchannels()
                sampwidth = wf.getsampwidth()
                framerate = wf.getframerate()
                if n_channels == 1 and sampwidth == 2 and framerate == sample_rate:
                    return wf.readframes(wf.getnframes())
        except Exception:
            pass

        # Format mismatch or reading error: resample with FFmpeg
        resampled_tmp = audio_path.with_suffix(".resampled.wav")
        resample_cmd = [
            self.config.ffmpeg_path,
            "-y",
            "-i", str(audio_path),
            "-acodec", "pcm_s16le",
            "-ac", "1",
            "-ar", str(sample_rate),
            str(resampled_tmp),
        ]
        subprocess.run(resample_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

        try:
            with wave.open(str(resampled_tmp), "rb") as wf:
                frames = wf.readframes(wf.getnframes())
            return frames
        finally:
            if resampled_tmp.is_file():
                try:
                    resampled_tmp.unlink()
                except OSError:
                    pass

    def assemble_timeline(
        self,
        synchronized_segments: List[SynchronizedSegment],
        total_duration: float,
        output_wav_path: Path,
    ) -> Path:
        """
        Assemble all synchronized segments onto an absolute timeline.
        Key guarantees:
        - Sample-accurate positioning directly at start_sample = round(start * sample_rate)
        - Zero cumulative timing drift over long videos
        - Intelligent crossfade mixing when segments overlap, preventing clicks & distortion
        - Audio canvas length matches total_duration exactly
        """
        output_wav_path.parent.mkdir(parents=True, exist_ok=True)
        sample_rate = self.config.sample_rate

        # Calculate exact total canvas size in samples
        total_samples = max(int(round(total_duration * sample_rate)), sample_rate)

        if np is not None:
            canvas = np.zeros(total_samples, dtype=np.int16)
        else:
            import array
            canvas = array.array("h", [0] * total_samples)

        # Sort segments by start timestamp to ensure strictly sequential placement
        sorted_segments = sorted(synchronized_segments, key=lambda s: (s.start, s.end))

        logger.debug(
            f"Assembling audio timeline: {total_duration:.3f}s ({total_samples} samples at {sample_rate}Hz)"
        )

        last_end_sample = 0
        for i, seg in enumerate(sorted_segments):
            if not seg.audio_path.is_file():
                continue

            try:
                raw_frames = self._ensure_correct_wav_format(seg.audio_path, sample_rate)
            except Exception as e:
                logger.error(f"Failed to read or resample segment {seg.id} audio: {e}")
                continue

            # Calculate absolute sample position (Rule #12)
            ideal_start_sample = max(0, int(round(seg.start * sample_rate)))
            if ideal_start_sample >= total_samples:
                continue

            # Overlap prevention (Rule #14): If previous sentence is still playing by up to 0.40s,
            # nudge start slightly to let previous sentence complete naturally.
            # At any silence gap, it automatically resets to ideal_start_sample with ZERO drift.
            if ideal_start_sample < last_end_sample and (last_end_sample - ideal_start_sample) <= int(0.40 * sample_rate):
                start_sample = min(total_samples - 1, last_end_sample + int(0.04 * sample_rate))
            else:
                start_sample = ideal_start_sample

            if np is not None:
                seg_samples = np.frombuffer(raw_frames, dtype=np.int16).copy()
                available_len = min(len(seg_samples), total_samples - start_sample)
                if available_len <= 0:
                    continue
                seg_samples = seg_samples[:available_len]
                end_sample = start_sample + available_len
                last_end_sample = end_sample

                # Check if this segment overlaps with the next segment's start
                next_start_sample = (
                    max(0, int(round(sorted_segments[i + 1].start * sample_rate)))
                    if (i + 1 < len(sorted_segments))
                    else total_samples
                )

                if end_sample > next_start_sample and next_start_sample > start_sample:
                    # Overlap detected between segment i and segment i+1
                    overlap_len = end_sample - next_start_sample
                    overlap_start = next_start_sample - start_sample
                    logger.debug(
                        f"Overlap detected: Segment {seg.id} extends {overlap_len / sample_rate:.3f}s into next segment. Applying soft intelligible ducking."
                    )
                    # Softly attenuate the overlapping tail rather than cutting off the sentence
                    duck_len = min(overlap_len, len(seg_samples) - overlap_start)
                    if duck_len > 1:
                        attenuation = np.linspace(1.0, 0.35, duck_len, dtype=np.float32)
                        seg_samples[overlap_start : overlap_start + duck_len] = (
                            seg_samples[overlap_start : overlap_start + duck_len] * attenuation
                        ).astype(np.int16)

                # Saturation addition: prevents hard clipping and pops in overlap regions
                existing = canvas[start_sample:end_sample].astype(np.int32)
                incoming = seg_samples.astype(np.int32)
                mixed = np.clip(existing + incoming, -32768, 32767).astype(np.int16)
                canvas[start_sample:end_sample] = mixed

            else:
                import array
                seg_samples = array.array("h")
                seg_samples.frombytes(raw_frames)
                end_sample = min(total_samples, start_sample + len(seg_samples))
                last_end_sample = end_sample
                length = end_sample - start_sample

                for k in range(length):
                    pos = start_sample + k
                    val = canvas[pos] + seg_samples[k]
                    canvas[pos] = max(-32768, min(32767, val))

        # Write assembled canvas to target WAV
        with wave.open(str(output_wav_path), "wb") as out_wf:
            out_wf.setnchannels(1)
            out_wf.setsampwidth(2)
            out_wf.setframerate(sample_rate)
            out_wf.writeframes(canvas.tobytes())

        if not output_wav_path.is_file() or output_wav_path.stat().st_size == 0:
            raise RuntimeError(f"Assembled dubbed audio file is missing or empty at {output_wav_path}")

        final_dur = get_media_duration(
            output_wav_path, self.config.ffprobe_path, self.config.ffmpeg_path
        )
        logger.debug(f"Dubbed audio track assembled: {final_dur:.3f}s ({output_wav_path.name})")

        return output_wav_path

    def synchronize(
        self,
        tts_segments: List[TTSSegment],
        total_duration: float,
        temp_dir: Path,
        output_wav_path: Path,
        cleanup_intermediates: bool = False,
    ) -> Path:
        """
        Full synchronization pipeline:
        - Parallel tempo adjustment across CPU cores
        - Reuses cached segment adjustments
        - Assembles sample-accurate timeline
        - Optionally prunes temporary intermediate segment WAVs
        """
        if output_wav_path.is_file() and output_wav_path.stat().st_size > 1024 and not self.config.force and not self.config.fresh:
            logger.info("Using cached dubbed audio track.")
            return output_wav_path

        sync_segments_dir = temp_dir / "sync_segments"
        sync_segments_dir.mkdir(parents=True, exist_ok=True)

        # Sort segments by start timestamp
        sorted_tts = sorted(tts_segments, key=lambda s: (s.start, s.end))

        def process_single_segment(item) -> SynchronizedSegment:
            i, seg = item
            seg_out = sync_segments_dir / f"sync_{seg.id:04d}.wav"
            next_start = sorted_tts[i + 1].start if (i + 1 < len(sorted_tts)) else None
            return self.adjust_segment_tempo(
                segment=seg,
                output_wav=seg_out,
                next_start=next_start,
                total_duration=total_duration,
            )

        import os
        from concurrent.futures import ThreadPoolExecutor
        workers = min(8, max(1, os.cpu_count() or 4))

        if len(sorted_tts) > 1:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                # executor.map guarantees preservation of input order
                synced_list = list(executor.map(process_single_segment, enumerate(sorted_tts)))
        else:
            synced_list = [process_single_segment((0, sorted_tts[0]))] if sorted_tts else []

        assembled_path = self.assemble_timeline(synced_list, total_duration, output_wav_path)

        # Cleanup temporary segment WAVs to conserve disk space on long videos
        if cleanup_intermediates and sync_segments_dir.is_dir():
            logger.debug("Cleaning up intermediate synchronized WAV segments to conserve disk space...")
            for f in sync_segments_dir.glob("*.wav"):
                try:
                    f.unlink()
                except OSError:
                    pass

        return assembled_path
