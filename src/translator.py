"""
Translation module with pluggable backends.
Translates transcript segments into natural English while preserving timestamps and original text.
"""

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from src.config import DubbingConfig
from src.transcriber import TranscriptSegment
from src.utils import load_json, save_json


logger = logging.getLogger("dubbing")


@dataclass
class TranslatedSegment:
    id: int
    start: float
    end: float
    original_text: str
    translated_text: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TranslatedSegment":
        return cls(
            id=data.get("id", 0),
            start=float(data.get("start", 0.0)),
            end=float(data.get("end", 0.0)),
            original_text=data.get("original_text", ""),
            translated_text=data.get("translated_text", ""),
        )


class BaseTranslator(ABC):
    """Abstract base class for translation engines."""

    @abstractmethod
    def translate_text(self, text: str, source_lang: str, target_lang: str) -> str:
        """Translate a single piece of text."""
        pass

    def translate_batch(
        self, texts: List[str], source_lang: str, target_lang: str
    ) -> List[str]:
        """Default sequential batch translation, can be overridden by backends."""
        return [self.translate_text(t, source_lang, target_lang) for t in texts]


def detect_script_lang(text: str) -> Optional[str]:
    """Detect non-Latin script family to route translation accurately."""
    if any("\u0400" <= c <= "\u04FF" for c in text):
        return "ru"
    if any("\u0900" <= c <= "\u097F" for c in text):
        return "hi"
    if any("\u0C00" <= c <= "\u0C7F" for c in text):
        return "te"
    if any("\u0B80" <= c <= "\u0BFF" for c in text):
        return "ta"
    if any("\u0C80" <= c <= "\u0CFF" for c in text):
        return "kn"
    if any("\u0D00" <= c <= "\u0D7F" for c in text):
        return "ml"
    if any("\u0980" <= c <= "\u09FF" for c in text):
        return "bn"
    if any("\u0600" <= c <= "\u06FF" for c in text):
        return "ar"
    if any("\u4E00" <= c <= "\u9FFF" or "\u3040" <= c <= "\u30FF" for c in text):
        return "zh"
    return None


CYRILLIC_TO_LATIN = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
    'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
    'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
    'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'shch',
    'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
    'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D', 'E': 'E', 'Ё': 'Yo',
    'Ж': 'Zh', 'З': 'Z', 'И': 'I', 'Й': 'Y', 'К': 'K', 'Л': 'L', 'М': 'M',
    'Н': 'N', 'О': 'O', 'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T', 'У': 'U',
    'Ф': 'F', 'Х': 'Kh', 'Ц': 'Ts', 'Ч': 'Ch', 'Ш': 'Sh', 'Щ': 'Shch',
    'Ъ': '', 'Ы': 'Y', 'Ь': '', 'Э': 'E', 'Ю': 'Yu', 'Я': 'Ya'
}


def transliterate_to_latin(text: str) -> str:
    """Transliterate Cyrillic or foreign characters to readable Latin phonemes."""
    out = []
    for c in text:
        if c in CYRILLIC_TO_LATIN:
            out.append(CYRILLIC_TO_LATIN[c])
        else:
            out.append(c)
    return "".join(out)


class ResilientTranslatorBackend(BaseTranslator):
    """
    Production-ready translation backend combining Google Translate with
    automatic fallback to MyMemoryTranslator and retry backoff.
    """

    MYMEMORY_LANG_MAP = {
        "de": "de-DE",
        "fr": "fr-FR",
        "hi": "hi-IN",
        "te": "te-IN",
        "ta": "ta-IN",
        "kn": "kn-IN",
        "ml": "ml-IN",
        "bn": "bn-IN",
        "es": "es-ES",
        "it": "it-IT",
        "ja": "ja-JP",
        "zh": "zh-CN",
        "ru": "ru-RU",
        "pt": "pt-PT",
        "nl": "nl-NL",
        "pl": "pl-PL",
        "tr": "tr-TR",
        "ar": "ar-SA",
        "en": "en-US",
    }

    def __init__(self):
        try:
            from deep_translator import GoogleTranslator, MyMemoryTranslator
            self._google_cls = GoogleTranslator
            self._mymemory_cls = MyMemoryTranslator
        except ImportError:
            raise RuntimeError(
                "deep-translator is not installed. Please install it using: pip install deep-translator"
            )

    def _translate_google_api(self, text: str, source_lang: str, target_lang: str) -> Optional[str]:
        """High-performance direct Google Translate API (fast, reliable, no HTML scraping)."""
        import requests
        try:
            url = "https://clients5.google.com/translate_a/t"
            params = {
                "client": "dict-chrome-ex",
                "sl": source_lang,
                "tl": target_lang,
                "q": text,
            }
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            resp = requests.get(url, params=params, headers=headers, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                res = None
                if isinstance(data, list) and data:
                    if isinstance(data[0], list) and data[0]:
                        res = str(data[0][0]).strip()
                    elif isinstance(data[0], str):
                        res = str(data[0]).strip()
                if res and not (target_lang.lower().startswith("en") and detect_script_lang(res)):
                    return res
        except Exception as e:
            logger.debug(f"Google Translate API failed for '{text[:20]}': {e}")
        return None

    def _translate_mymemory(self, text: str, source_lang: str, target_lang: str) -> Optional[str]:
        """Translate using MyMemory as secondary high-reliability backend."""
        try:
            src = self.MYMEMORY_LANG_MAP.get(source_lang, f"{source_lang}-{source_lang.upper()}")
            tgt = self.MYMEMORY_LANG_MAP.get(target_lang, "en-US")
            translator = self._mymemory_cls(source=src, target=tgt)
            res = translator.translate(text)
            if res and res.strip() and not res.startswith("MYMEMORY WARNING"):
                # Reject if MyMemory merely echoed non-Latin text without translation
                if res.strip() == text.strip() and detect_script_lang(text) is not None:
                    return None
                return res.strip()
        except Exception as e:
            logger.debug(f"MyMemory fallback failed for '{text[:20]}': {e}")
        return None

    def translate_text(self, text: str, source_lang: str, target_lang: str) -> str:
        if not text or not text.strip():
            return ""
        if source_lang.lower().strip() == target_lang.lower().strip():
            return text

        # Detect non-Latin script if different from declared source language
        script_lang = detect_script_lang(text)
        effective_src = script_lang or source_lang

        # Attempt 1: High-performance Google API
        api_res = self._translate_google_api(text, effective_src, target_lang)
        if api_res:
            return api_res

        # Attempt 2: Google Translate via deep_translator
        try:
            translator = self._google_cls(source=effective_src, target=target_lang)
            translated = translator.translate(text)
            if translated and translated.strip():
                if not (target_lang.lower().startswith("en") and detect_script_lang(translated)):
                    return translated.strip()
        except Exception as e:
            logger.debug(f"Google Translate error ('{text[:20]}'): {e}. Trying MyMemory fallback.")

        # Attempt 3: MyMemory fallback with effective script language
        fallback = self._translate_mymemory(text, effective_src, target_lang)
        if fallback:
            if not (target_lang.lower().startswith("en") and detect_script_lang(fallback)):
                return fallback

        # Attempt 3: If effective_src differed, try original source_lang on MyMemory
        if effective_src != source_lang:
            fallback2 = self._translate_mymemory(text, source_lang, target_lang)
            if fallback2 and not (target_lang.lower().startswith("en") and detect_script_lang(fallback2)):
                return fallback2

        # Attempt 4: If target is English and text still contains Cyrillic, transliterate to Latin
        if target_lang.lower().startswith("en"):
            translit = transliterate_to_latin(text)
            if translit != text and not detect_script_lang(translit):
                logger.info(f"Transliterated segment text to Latin for TTS: '{text}' -> '{translit}'")
                return translit

        # Attempt 5: Fallback to original
        logger.warning(f"Translation unavailable for '{text[:30]}...'. Keeping original text.")
        return text


GoogleTranslatorBackend = ResilientTranslatorBackend


class MockTranslatorBackend(BaseTranslator):
    """Deterministic mock translator for testing and offline development."""

    def __init__(self, prefix: str = "[EN] "):
        self.prefix = prefix

    def translate_text(self, text: str, source_lang: str, target_lang: str) -> str:
        if not text or not text.strip():
            return ""
        if source_lang.lower().startswith("en"):
            return text
        return f"{self.prefix}{text}"


class Translator:
    """Orchestrates segment-level translation with caching and progress updates."""

    def __init__(self, config: DubbingConfig):
        self.config = config
        self.backend = self._create_backend(config.translation_backend)

    def _create_backend(self, backend_name: str) -> BaseTranslator:
        name = backend_name.lower().strip()
        if name in ("mock", "test"):
            return MockTranslatorBackend()
        elif name == "google":
            return GoogleTranslatorBackend()
        else:
            logger.warning(f"Unknown translation backend '{backend_name}', falling back to Google.")
            return GoogleTranslatorBackend()

    def translate_segments(
        self,
        segments: List[TranscriptSegment],
        source_language: str,
        cache_path: Optional[Path] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> List[TranslatedSegment]:
        """
        Translate a list of TranscriptSegments to English.
        Supports incremental resumption, periodic checkpointing, and concurrent execution.
        """
        # Step 1: Check for existing full or partial cache with text-hash validation
        existing_translations: Dict[int, TranslatedSegment] = {}
        seg_map = {s.id: s for s in segments}

        if cache_path and cache_path.is_file() and not self.config.force and not self.config.fresh:
            cached_data = load_json(cache_path)
            if cached_data and isinstance(cached_data, list):
                valid_cache = True
                loaded_segments = []
                for item in cached_data:
                    c_seg = TranslatedSegment.from_dict(item)
                    # Verify that segment ID exists and original text matches exactly
                    if c_seg.id in seg_map and c_seg.original_text.strip() == seg_map[c_seg.id].text.strip():
                        existing_translations[c_seg.id] = c_seg
                        loaded_segments.append(c_seg)
                    else:
                        valid_cache = False

                if valid_cache and len(loaded_segments) == len(segments):
                    logger.info("Using verified cached translated segments.")
                    return sorted(loaded_segments, key=lambda s: (s.start, s.end))

                if existing_translations:
                    logger.info(
                        f"Resuming translation: {len(existing_translations)}/{len(segments)} segments matched cache."
                    )

        total = len(segments)
        # Language code normalization for deep-translator
        lang = source_language.lower().strip()
        lang_map = {
            "jw": "jv",  # Javanese
            "iw": "he",  # Hebrew
            "in": "id",  # Indonesian
        }
        lang = lang_map.get(lang, lang)

        # Separate segments into already translated and remaining
        needed_segments = [s for s in segments if s.id not in existing_translations]
        result_dict: Dict[int, TranslatedSegment] = dict(existing_translations)

        if not needed_segments:
            ordered = [result_dict[s.id] for s in sorted(segments, key=lambda s: (s.start, s.end))]
            return ordered

        completed = len(result_dict)
        if progress_callback:
            progress_callback(completed, total)

        def translate_single(seg: TranscriptSegment) -> TranslatedSegment:
            original = seg.text.strip()
            if not original:
                return TranslatedSegment(
                    id=seg.id,
                    start=seg.start,
                    end=seg.end,
                    original_text="",
                    translated_text="",
                )

            # If translation backend is mock, run mock translation directly (for tests)
            if getattr(self.config, "translation_backend", "") == "mock":
                translated = self.backend.translate_text(
                    text=original,
                    source_lang=lang,
                    target_lang=self.config.target_language,
                )
            # If whisper_task == "translate" and text is already in Latin/English characters,
            # it was translated directly from audio by Whisper!
            elif getattr(self.config, "whisper_task", "transcribe") == "translate" and detect_script_lang(original) is None:
                translated = original
            else:
                translated = self.backend.translate_text(
                    text=original,
                    source_lang=lang,
                    target_lang=self.config.target_language,
                )

                # Quality check: if translation echoed foreign script or unchanged text in another language
                if (not translated or translated.strip() == original) and lang != "en":
                    # Retry with auto source detection
                    auto_trans = self.backend.translate_text(
                        text=original,
                        source_lang="auto",
                        target_lang=self.config.target_language,
                    )
                    if auto_trans and auto_trans.strip() != original:
                        translated = auto_trans

            if not translated or not translated.strip():
                translated = original

            return TranslatedSegment(
                id=seg.id,
                start=seg.start,
                end=seg.end,
                original_text=original,
                translated_text=translated.strip(),
            )

        from concurrent.futures import ThreadPoolExecutor, as_completed
        max_workers = min(6, len(needed_segments)) if len(needed_segments) > 1 else 1

        checkpoint_counter = 0
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_seg = {executor.submit(translate_single, seg): seg for seg in needed_segments}
            for future in as_completed(future_to_seg):
                translated_seg = future.result()
                result_dict[translated_seg.id] = translated_seg
                completed += 1
                checkpoint_counter += 1

                if progress_callback:
                    progress_callback(completed, total)

                # Incremental checkpoint every 25 segments for long videos
                if cache_path and checkpoint_counter % 25 == 0:
                    current_ordered = [
                        result_dict[s.id] for s in sorted(segments, key=lambda s: (s.start, s.end)) if s.id in result_dict
                    ]
                    save_json([asdict(s) for s in current_ordered], cache_path)

        ordered_results = [result_dict[s.id] for s in sorted(segments, key=lambda s: (s.start, s.end))]

        if cache_path:
            save_json([asdict(s) for s in ordered_results], cache_path)
            logger.debug(f"Saved translated segments to {cache_path}")

        return ordered_results
