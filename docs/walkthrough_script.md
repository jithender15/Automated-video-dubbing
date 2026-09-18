# 2-Minute Video Walkthrough Script

This script is designed for a concise, natural, professional 2-minute video presentation demonstrating the Automated Video Dubbing System.

---

### [0:00 – 0:20] Introduction
**Visual**: Show project in IDE terminal / title slide.  
**Spoken Script**:  
> "Hi everyone. Today I'm presenting the Automated Video Dubbing System. This project takes any foreign language YouTube video—whether in German, French, Hindi, or Spanish—and automatically transforms it into a fully dubbed, natural English video while preserving the original visual stream, speech cadence, and timing."

---

### [0:20 – 0:50] Architecture & Pipeline
**Visual**: Show architecture diagram in README or slide.  
**Spoken Script**:  
> "Our pipeline operates in seven clean, decoupled stages:  
> First, `yt-dlp` fetches the high-quality video and audio stream.  
> Second, FFmpeg extracts a standardized 16kHz mono WAV file.  
> Third, OpenAI Whisper detects the source language and generates segment-level timestamps.  
> Fourth, a modular translation engine converts the sentences into natural English while keeping the original text alongside for auditing.  
> Fifth, Microsoft Edge Neural TTS synthesizes human-grade English speech for each segment.  
> Sixth, our synchronizer uses FFmpeg `atempo` adjustments and an absolute timeline canvas to ensure zero cumulative timing drift.  
> And finally, FFmpeg multiplexes the dubbed audio with the original video stream without re-encoding."

---

### [0:50 – 1:20] Live Demonstration
**Visual**: Show terminal running `python src/main.py "https://www.youtube.com/watch?v=..." --benchmark`.  
**Spoken Script**:  
> "Let's run the system with a single command:  
> `python src/main.py [YouTube URL] --benchmark`  
> Notice the clean terminal output. We see each stage progress smoothly: downloading the video, extracting audio, transcribing with Whisper, translating to English, synthesizing speech, and sample-accurately synchronizing onto the audio timeline.  
> Because the system implements intermediate file caching, long jobs can resume instantly if interrupted."

---

### [1:20 – 1:45] Output Demonstration
**Visual**: Open the resulting video in `outputs/` and play a 15-second clip showing synchronized English speech.  
**Spoken Script**:  
> "Here is our final output video in `outputs/`. Let's play it.  
> Notice that the original video visuals are 100% preserved because we used stream copying rather than re-encoding. The dubbed English voice begins and ends in close alignment with the speaker's original gestures and scene changes, with no audio drift over time."

---

### [1:45 – 2:00] Technical Decisions & Limitations
**Visual**: Show summary slide or README benchmark table.  
**Spoken Script**:  
> "Key technical decisions included avoiding re-encoding to keep processing fast even for 2-hour videos, and using absolute timeline placement to prevent drift.  
> While fast-speaking segments are tempo-clamped to preserve natural tone, future improvements include multi-speaker diarization and voice cloning.  
> Thank you for watching!"
