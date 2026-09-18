# 2-Minute Demo Checklist

Use this checklist during your screen recording to ensure all required aspects are demonstrated smoothly.

---

## Pre-Recording Setup
- [ ] Open IDE / terminal in `automated-video-dubbing/`.
- [ ] Activate Python environment: `.\.venv\Scripts\Activate.ps1`.
- [ ] Have a target foreign language YouTube URL ready on your clipboard (e.g., German, French, or Hindi video).
- [ ] Ensure media player (VLC or Windows Media Player) is ready to play the generated video.
- [ ] Clear old temporary files or use a new video ID so live progress is visible.

---

## Screen Recording Steps

### 1. Title & Introduction (0:00 - 0:20)
- [ ] Show the project directory structure in terminal or file explorer (`src/`, `downloads/`, `temp/`, `outputs/`, `tests/`).
- [ ] Mention project goal: Fully automated foreign-language to English video dubbing.

### 2. Architecture & Pipeline (0:20 - 0:50)
- [ ] Briefly show the 7-stage pipeline diagram in `README.md`.
- [ ] Highlight:
  - `yt-dlp` for download
  - OpenAI Whisper for segment timestamps
  - Pluggable translation
  - Microsoft Edge Neural TTS
  - FFmpeg `atempo` + absolute timeline canvas (zero drift)
  - `-c:v copy` muxing (fast, lossless video)

### 3. Execution (0:50 - 1:20)
- [ ] Run the CLI command:
  ```powershell
  python src/main.py "YOUR_YOUTUBE_URL" --benchmark
  ```
- [ ] Point out the terminal output:
  - `[1/7] Downloading video...`
  - `[2/7] Extracting audio...`
  - `[3/7] Transcribing speech...` (Show detected language & segment count)
  - `[4/7] Translating to English...`
  - `[5/7] Generating English speech...`
  - `[6/7] Synchronizing audio...`
  - `[7/7] Creating final dubbed video...`
- [ ] Highlight the benchmark timing report at the end.

### 4. Output Demonstration (1:20 - 1:45)
- [ ] Open `outputs/<video_title>_dubbed.mp4` in media player.
- [ ] Play a short section with clear speech.
- [ ] Show that the visual quality is completely intact and English speech is audible and synchronized.
- [ ] Show `temp/<video_id>/transcript.json` and `translated_segments.json` to prove transcripts and translations are preserved.

### 5. Wrap Up & Limitations (1:45 - 2:00)
- [ ] Mention caching efficiency for 30-minute and 2-hour long videos.
- [ ] Note future enhancements: Speaker diarization and voice cloning.
