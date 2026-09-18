# Automated Video Dubbing System

An enterprise-grade, fully modular Python system for automatically translating and dubbing foreign-language YouTube videos (German, French, Hindi, Spanish, etc.) into natural, synchronized English speech while preserving original visuals, timing cadence, and video streams.

---

## 1. Overview
The Automated Video Dubbing System provides an autonomous end-to-end pipeline that takes any foreign-language YouTube URL, extracts audio, transcribes speech with segment-level timestamps, translates sentences into fluent English, synthesizes speech with Microsoft Edge Neural TTS voices, aligns and synchronizes the audio track to eliminate drift, and multiplexes the new English audio into the original video stream without re-encoding.

---

## 2. Features
- **Zero-Friction CLI**: Single command execution: `python src/main.py "YOUTUBE_URL"`.
- **Multilingual Transcription**: Powered by OpenAI Whisper for robust speech recognition and automatic source language detection across 90+ languages.
- **Segment-Level Synchronization**: Preserves original speech start/stop timestamps and employs sample-accurate absolute canvas positioning to guarantee **zero cumulative drift**.
- **Intelligent Tempo Adjustment**: Uses FFmpeg's `atempo` filter to adapt speech duration to the video timeline within natural perceptual boundaries (0.80x–1.35x).
- **Human-Grade Neural TTS**: Utilizes Microsoft Edge Neural TTS voices (e.g., `en-US-AriaNeural`) for expressive, high-fidelity English speech.
- **Lossless Video Muxing**: Employs FFmpeg stream copying (`-c:v copy`) to preserve 100% of original visual quality and complete muxing in seconds.
- **Resumable File-Based Caching**: Caches intermediate downloads, transcripts, translations, TTS clips, and audio tracks to allow instant resumption of long jobs (30-minute and 2-hour videos).
- **Built-in Benchmarking**: `--benchmark` flag profiles execution duration per stage and persists performance metrics to disk.

---

## 3. Architecture

```
YouTube URL
    ↓
[1/7] yt-dlp (Download video & audio stream)
    ↓
[2/7] FFmpeg Audio Extraction (16kHz mono WAV)
    ↓
[3/7] OpenAI Whisper (Detect language & transcribe with segment timestamps)
    ↓
[4/7] Pluggable Translator (Google Translate / MarianMT / IndicTrans2)
    ↓
[5/7] Microsoft Edge Neural TTS (Asynchronous English speech synthesis)
    ↓
[6/7] Synchronizer (atempo adjustment & absolute timeline assembly)
    ↓
[7/7] FFmpeg Video Processor (-c:v copy -c:a aac muxing)
    ↓
Final Dubbed MP4 Video (outputs/)
```

---

## 4. Technologies
- **Python 3.11**: Core runtime environment.
- **yt-dlp**: High-performance, robust video and audio extraction from YouTube.
- **OpenAI Whisper**: Speech-to-text transcription with millisecond segment timestamps.
- **deep-translator**: Pluggable multilingual translation backend (100+ languages supported out of the box).
- **edge-tts**: Python interface for Microsoft Edge Neural Text-to-Speech service.
- **FFmpeg**: Industry-standard audio/video processing, tempo scaling, and lossless stream multiplexing.
- **Pytest**: Comprehensive unit and integration test suite.

---

## 5. Requirements
- Operating System: Windows 10/11, macOS, or Linux.
- Python: Python 3.10 or 3.11.
- FFmpeg & FFprobe: Must be installed and accessible in PATH.
- Internet Connection: Required for video downloading, translation, and TTS synthesis.

---

## 6. Installation

### 1. Clone or Open the Repository
```powershell
cd automated-video-dubbing
```

### 2. Set Up Virtual Environment
```powershell
# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows (PowerShell):
.\.venv\Scripts\Activate.ps1
# Linux / macOS:
source .venv/bin/activate
```

### 3. Install Dependencies
```powershell
pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

---

## 7. FFmpeg Installation

FFmpeg is required for audio extraction, audio synchronization, and video muxing.

### Windows Installation (Recommended):
Using Windows Package Manager (WinGet):
```powershell
winget install Gyan.FFmpeg.Essentials
```
After installation, restart your terminal to reload PATH. Verify with:
```powershell
ffmpeg -version
ffprobe -version
```

*Manual Windows Option*:
Download the essentials build from [gyan.dev/ffmpeg/builds](https://www.gyan.dev/ffmpeg/builds/), extract to `C:\ffmpeg`, and add `C:\ffmpeg\bin` to your System PATH, or place `ffmpeg.exe` and `ffprobe.exe` into a `bin/` directory inside this project.

### macOS Installation:
```bash
brew install ffmpeg
```

### Linux Installation (Ubuntu/Debian):
```bash
sudo apt update && sudo apt install ffmpeg
```

---

## 8. Usage

### Basic Dubbing
```powershell
python src/main.py "https://www.youtube.com/watch?v=VIDEO_ID"
```

### With Custom Whisper Model Size
```powershell
# Options: tiny, base, small, medium, large
python src/main.py "https://www.youtube.com/watch?v=VIDEO_ID" --model small
```

### With Custom TTS Voice
```powershell
# Example female voices: en-US-AriaNeural, en-GB-SoniaNeural
# Example male voices: en-US-GuyNeural, en-AU-WilliamNeural
python src/main.py "https://www.youtube.com/watch?v=VIDEO_ID" --voice en-US-GuyNeural
```

### With Stage Benchmarking
```powershell
python src/main.py "https://www.youtube.com/watch?v=VIDEO_ID" --benchmark
```

### Forcing Full Re-Processing (Ignoring Cache)
```powershell
python src/main.py "https://www.youtube.com/watch?v=VIDEO_ID" --force
```

---

## 9. Configuration

Configuration options can be customized via CLI arguments, environment variables, or a `.env` file:

| Option | Env Variable | Default | Description |
|---|---|---|---|
| Whisper Model | `WHISPER_MODEL` | `base` | Model size (`tiny`, `base`, `small`, `medium`, `large`) |
| TTS Voice | `TTS_VOICE` | `en-US-AriaNeural` | Microsoft Edge neural voice identifier |
| Translation Backend | `TRANSLATION_BACKEND` | `google` | Translation engine (`google`, `mock`, `marian`) |
| Download Directory | `DOWNLOAD_DIR` | `downloads` | Directory for downloaded videos |
| Temp Directory | `TEMP_DIR` | `temp` | Directory for cached transcripts and audio |
| Output Directory | `OUTPUT_DIR` | `outputs` | Directory for final dubbed videos |
| FFmpeg Binary | `FFMPEG_PATH` | `ffmpeg` | Path override for FFmpeg executable |

Copy `.env.example` to `.env` to set local overrides:
```powershell
cp .env.example .env
```

---

## 10. Output Structure

All outputs are neatly separated:
```
automated-video-dubbing/
├── downloads/
│   └── <video_title>_<video_id>.mp4
├── temp/
│   └── <video_id>/
│       ├── audio.wav
│       ├── transcript.json
│       ├── translated_segments.json
│       ├── tts/
│       │   ├── segment_0000.mp3
│       │   └── ...
│       ├── sync_segments/
│       │   ├── sync_0000.wav
│       │   └── ...
│       └── dubbed_audio.wav
├── outputs/
│   └── <video_title>_<video_id>_dubbed.mp4
└── logs/
    ├── dubbing_<timestamp>.log
    └── benchmark_<video_id>.json
```

---

## 11. Pipeline Explanation

1. **Downloader (`src/downloader.py`)**: Validates the YouTube URL format, checks cache, and downloads high-quality streams via `yt-dlp`.
2. **Audio Extraction (`src/audio.py`)**: Runs FFmpeg to strip the video and extract a 16kHz mono 16-bit PCM WAV.
3. **Transcriber (`src/transcriber.py`)**: Loads the Whisper model into memory (cached across runs) and produces segment-level timestamps (`start`, `end`, `text`).
4. **Translator (`src/translator.py`)**: Maps source language codes and translates sentences to English while preserving timestamps and keeping both original and translated text in `temp/<video_id>/translated_segments.json`.
5. **Synthesizer (`src/synthesizer.py`)**: Converts each segment into neural English speech with `edge-tts` and caches individual clips.
6. **Synchronizer (`src/synchronizer.py`)**: Measures synthesized audio durations, applies `atempo` filters where needed, and places samples at their absolute timestamp positions on a continuous PCM canvas.
7. **Video Processor (`src/video_processor.py`)**: Combines the original video stream with the dubbed audio track using `-c:v copy` and `-c:a aac`.

---

## 12. Synchronization Approach

A naive concatenation of TTS segments leads to **cumulative drift**, where later sentences become desynchronized by dozens of seconds. 

Our system solves this via a two-layer synchronization architecture:
1. **Duration Matching**:
   - For every segment, target duration is calculated as `target = segment.end - segment.start`.
   - If English speech is longer, the tempo is scaled using FFmpeg `atempo`:
     $$\text{tempo} = \min\left(\frac{\text{tts\_duration}}{\text{target\_duration}}, 1.35\right)$$
   - The factor is clamped between $0.80\times$ and $1.35\times$ to avoid distorting speech naturalness.
2. **Absolute Canvas Placement**:
   - A silent audio canvas of exact duration is initialized in RAM ($16000\text{ samples/sec} \times 2\text{ bytes/sample}$).
   - Each segment is placed at its **exact start sample**:
     $$\text{start\_sample} = \lfloor\text{segment.start} \times 16000\rfloor$$
   - Any silence between sentences in the original video is preserved, ensuring **zero accumulated drift across the entire timeline**.

---

## 13. Error Handling
- **Missing URL or Invalid URL**: Validated upfront with clear error messages.
- **FFmpeg Not Installed**: Checked on pipeline initialization; provides OS-specific setup commands rather than crashing.
- **Missing Audio or Speech**: Warns gracefully if Whisper detects 0 segments.
- **Translation / Network Errors**: Falls back to original text if a translation call fails, preventing crashes.
- **Video Re-encoding Fallback**: If stream copying (`-c:v copy`) fails due to incompatible container formats, the system automatically falls back to `-c:v libx264`.
- **Comprehensive Logging**: Human-friendly summaries appear in the terminal while verbose stack traces and commands are recorded in `logs/`.

---

## 14. Performance & Caching
- **Model Reuse**: Whisper models are loaded once and retained in memory.
- **File-Based Caching**: Every stage writes intermediate state to `temp/<video_id>/`. Re-running a command checks cache and skips already completed steps.
- **Lossless Muxing**: Copying video streams takes under 3 seconds regardless of video length.
- **Linear Memory Footprint**: The 16kHz audio canvas for a 2-hour video requires only ~230 MB of RAM, easily running on modest machines.

---

## 15. Testing

A complete test suite is provided in `tests/`:

```powershell
# Run all unit and integration tests
pytest tests -v
```

Tests include:
- `test_downloader.py`: URL validation, video ID extraction, filename sanitization.
- `test_translator.py`: Segment serialization, mock translator, language normalization.
- `test_synchronizer.py`: Tempo calculations, clamping boundaries, sample-accurate timeline assembly.
- `test_pipeline.py`: Full mock integration test verifying all 7 stages and cache behavior.

---

## 16. Limitations
- **Single-Voice Output**: The current core pipeline applies a single configured voice across all speakers in the video.
- **Speech Speed Bound**: In segments where English sentences are significantly longer than the original foreign speech, speech speed is capped at $1.35\times$ to preserve naturalness, which may cause minor boundary overflow into subsequent pauses.
- **Background Music/Effects**: Original background audio and sound effects are replaced along with speech.

---

## 17. Optional Enhancements
1. **Speaker Diarization**: Multi-speaker identification (e.g. using `pyannote.audio`) to assign distinct male/female English voices.
2. **Background Track Separation**: Demucs or Spleeter integration to isolate vocals from music/BGM and preserve original background sound.
3. **Voice Cloning**: Integrating XTTS or Coqui to clone the original speaker's vocal timbre into English.
4. **Subtitle Generation**: Generating matching synchronized `.srt` or `.vtt` subtitles alongside dubbed video.

---

## 18. Audio Synchronization, Quality & Video Playability Architecture

Following a systematic 17-Phase quality audit, the Automated Video Dubbing System features robust architectural protections against speech cut-offs, container corruption, audio drift, and cache contamination:

### Root Cause Analysis & Technical Solutions

| Problem Identified | Root Cause | Technical Solution Implemented |
| :--- | :--- | :--- |
| **1. English Not Spoken / Foreign Echoes** | Upstream translation failure or rate limits returned original foreign text, causing Edge-TTS to speak foreign words phonetically or skip. | Added direct Google Translate API endpoint (`clients5.google.com/translate_a/t`) with zero rate limits, automatic fallback to `source_lang="auto"`, and expanded script mapping for Asian/Indian languages. |
| **2. Nonsensical Translation / Cache Collisions** | Generic cache filenames (`segment_0001.mp3`) caused stale cached translations from previous videos to be reused. | Content-hash validation (`original_text.strip()` match) and isolated job directories (`temp/jobs/<video_id>_<url_hash>/`). |
| **3. Speech Cut-Offs at Boundaries** | Previous synchronizer forcibly zeroed audio (`seg_samples[overlap_start + decay_len:] = 0`) when a sentence exceeded its time window. | Replaced destructive zeroing with soft crossfade ducking (attenuation down to 0.35) and saturation mixing so all words remain clearly audible. |
| **4. Destructive Audio Overlapping** | Long sentences translated into English exceeded the target window, causing overlap distortion. | Dynamic tempo adjustment up to 1.45x combined with soft crossfade ducking and non-destructive saturation mixing preventing digital clipping. |
| **5. Damaged or Unplayable MP4 Video** | yt-dlp downloaded VP9/AV1 video streams which were copied directly into MP4 containers (`-c:v copy`), failing on Windows Media Player and QuickTime. | Format selector prioritizes standard H.264 (`avc1`); automatic codec detection transcodes non-standard codecs to `libx264` to guarantee 100% universal playability. |
| **6. Audio Several Seconds Ahead / Behind** | Variable sample rates or missing container PTS sync during audio extraction caused timing drift over long videos. | Audio extracted with `-af aresample=async=1000` to synchronize audio PTS with container timeline; absolute sample-accurate placement on the timeline canvas. |
| **7. Final Video Stopping Early** | FFmpeg muxing command contained `-shortest`. If dubbed audio was even 0.05s shorter than video, the entire video stream was truncated. | Removed `-shortest` completely; added `apad=whole_dur` audio padding filter to guarantee the audio stream never terminates before the video stream. |
| **8. Cache Contamination Across Runs** | Overlapping file names across different test videos led to stale segment reuse. | Added `--fresh` CLI flag and job-isolated workspace directories (`temp/jobs/<video_id>_<hash>/`). |

---

## 19. 12-Point Automated Output Validation Protocol

Every video processed by the pipeline automatically undergoes a rigorous 12-point validation check via `src/validator.py`:

1. **File Existence**: Confirms MP4 file is written to disk.
2. **File Size**: Confirms non-zero payload (> 0 bytes).
3. **Container Integrity**: Inspects MP4 container headers via FFprobe.
4. **Video Stream Verification**: Confirms presence of a valid video stream.
5. **Audio Stream Verification**: Confirms presence of a valid stereo/mono audio stream.
6. **Video Codec Compatibility**: Verifies standard codec (e.g. H.264).
7. **Audio Codec Compatibility**: Verifies standard AAC audio.
8. **Duration Verification**: Measures video duration against expected source duration.
9. **Audio Duration Match**: Measures dubbed audio stream length.
10. **A/V Synchronization Delta**: Ensures video and audio duration difference is $\le 0.50$ seconds.
11. **Decode Playability**: Executes a complete FFmpeg decode pass (`-f null -`) to catch corrupt frames.
12. **Structured Reporting**: Prints a terminal report and logs results before concluding.

---

## 20. Project Structure

```
automated-video-dubbing/
├── src/
│   ├── __init__.py
│   ├── main.py              # CLI entry point (supports --fresh, --benchmark)
│   ├── config.py            # Central configuration & job-scoped directory manager
│   ├── downloader.py        # yt-dlp downloader with H.264 stream prioritization
│   ├── audio.py             # FFmpeg audio extraction with PTS aresample
│   ├── transcriber.py       # OpenAI Whisper transcription & language detection
│   ├── translator.py        # Robust translation with content-hash validation
│   ├── synthesizer.py       # edge-tts neural synthesis with text-hashed clips
│   ├── synchronizer.py      # Zero-drift canvas assembler & soft crossfade ducking
│   ├── video_processor.py   # FFmpeg muxer with apad and automatic transcoding
│   ├── validator.py         # 12-point output integrity & playability validator
│   ├── pipeline.py          # Master orchestrator
│   └── utils.py             # Logging, timing, and formatting helpers
├── tests/
│   ├── test_downloader.py
│   ├── test_optimizations.py
│   ├── test_pipeline.py
│   ├── test_synchronizer.py
│   ├── test_translator.py
│   └── test_validator.py
├── downloads/
├── temp/
│   └── jobs/
├── outputs/
├── logs/
├── requirements.txt
├── requirements-dev.txt
├── README.md
├── .gitignore
└── .env.example
```

---

## 21. Troubleshooting

**Issue**: `ERROR: FFmpeg was not found.`  
*Solution*: Run `winget install Gyan.FFmpeg.Essentials` in PowerShell as administrator, restart terminal, and ensure `ffmpeg -version` works.

**Issue**: `Whisper takes a long time to transcribe.`  
*Solution*: Use `--model tiny` or `--model base` for faster execution on CPU.

**Issue**: `Audio does not play in Windows Media Player.`  
*Solution*: Output video is automatically encoded to standard H.264 + AAC. Running with `--fresh` ensures clean generation.

---

## 22. Future Improvements
- Add web UI interface using Streamlit or Gradio for drag-and-drop dubbing.
- Implement streaming transcription for live video streams.
- Integrate IndicTrans2 for specialized high-fidelity Indian language translation.
