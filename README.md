# BPC Dictation — Whisper Speech-to-Text Integration for UE5

This repository provides two Python scripts that add OpenAI Whisper-powered
speech-to-text capabilities to an Unreal Engine 5 project's chat system:

| Script | Purpose |
|---|---|
| `whisper_server.py` | HTTP server that UE5 Blueprints call to transcribe audio |
| `local_transcribe.py` | Standalone microphone → text tool for the developer machine |

---

## Prerequisites

- Python 3.9 or newer
- [ffmpeg](https://ffmpeg.org/download.html) installed and on your `PATH`
  (required by Whisper to decode audio)
- A working microphone (for local transcription or UE5 audio capture)

### Install Python dependencies

```bash
pip install -r requirements.txt
```

> **Note:** Installing `openai-whisper` will also download a PyTorch build.
> This can be several hundred MB on the first install.

---

## 1 — Whisper Server (`whisper_server.py`)

The server exposes a simple REST API so that **UE5 Blueprints** (or any HTTP
client) can request transcriptions without running Python inside UE5.

### Start the server

```bash
# Default: binds to 127.0.0.1:8765 using the 'base' Whisper model
python whisper_server.py

# Larger model for better accuracy (slower, uses more RAM/VRAM):
python whisper_server.py --model small

# Accept connections from other machines on the network:
python whisper_server.py --host 0.0.0.0 --port 8765

# Full options:
python whisper_server.py --help
```

### API Reference

#### `POST /transcribe`

Transcribe an audio file.

| Field | Type | Description |
|---|---|---|
| `audio` | multipart/form-data file | Audio file to transcribe (WAV, OGG, MP3, FLAC, …) |

**Success response (HTTP 200)**

```json
{ "text": "Hello, this is the transcribed text." }
```

**Error response (HTTP 400 / 500)**

```json
{ "error": "No audio file provided. POST the audio under the field name 'audio'." }
```

#### `GET /health`

Liveness check.

```json
{ "status": "ok" }
```

### Quick test with curl

```bash
# Record a WAV file with any recorder and then:
curl -X POST http://127.0.0.1:8765/transcribe \
     -F "audio=@recording.wav"
```

---

## 2 — Local Transcription (`local_transcribe.py`)

Use this script to transcribe speech directly from the microphone on your
development machine.  No UE5 connection needed.

```bash
# Push-to-talk (default): press ENTER to start, ENTER again to stop
python local_transcribe.py

# Save the transcription to a text file
python local_transcribe.py --output-file transcript.txt

# Continuous loop — keep recording until Ctrl+C
python local_transcribe.py --mode continuous

# Higher-accuracy model
python local_transcribe.py --model small

# Full options
python local_transcribe.py --help
```

### Available models

| Model | Parameters | Relative accuracy | Speed (CPU) |
|---|---|---|---|
| `tiny` | 39 M | ★☆☆☆☆ | Fastest |
| `base` | 74 M | ★★☆☆☆ | Fast (default) |
| `small` | 244 M | ★★★☆☆ | Moderate |
| `medium` | 769 M | ★★★★☆ | Slow |
| `large` | 1550 M | ★★★★★ | Slowest |

If you have a CUDA-capable GPU, Whisper will use it automatically.

---

## 3 — UE5 Blueprint Integration

The diagram below shows how the two systems connect.

```
  ┌─────────────────────────────┐         ┌──────────────────────────────┐
  │      UE5 Game (Blueprints)  │         │      whisper_server.py       │
  │                             │  POST   │                              │
  │  MicrophoneCapture ──────► WAV ──────►│  /transcribe                 │
  │                             │  JSON   │                              │
  │  Chat System ◄──── "text" ◄─┼─────────│  {"text": "…"}              │
  └─────────────────────────────┘         └──────────────────────────────┘
```

### Step-by-step Blueprint setup

> **Prerequisite:** Enable the **HTTP** and **VaRest** (or built-in JSON) plugins
> in your UE5 project settings.  The built-in HTTP module is sufficient.

#### Step 1 — Record microphone audio in Blueprint

1. Add a **Voice Capture** component to your Actor (or use `StartRecordingOutput`
   from `AudioMixerBlueprintLibrary`).
2. Call `StartRecordingOutput` when the player activates push-to-talk.
3. Call `StopRecordingOutput` to finish.  Bind the **OnAudioFinished** delegate
   to get the recorded `USoundWave`.
4. Export the `USoundWave` to a temporary WAV file using
   `ExportWaveFile` (available via the **AudioCaptureCore** module or a small
   C++ helper — see below).

#### Step 2 — Send the WAV file to the server

Inside the **OnAudioFinished** event graph:

```
[OnAudioFinished] → [Construct HTTP Request]
                       Verb: POST
                       URL:  http://127.0.0.1:8765/transcribe
                    → [Set Content From File]  ← (path from Step 1)
                       Content-Type: multipart/form-data
                    → [Process Request]
                    → [OnRequestComplete] → [Parse JSON Response]
                                             Field: "text"
                                          → [Send to Chat System]
```

#### Step 3 — Parse the JSON response

Use the **JSON Query** Blueprint library (or the built-in
`UBlueprintJsonObject`) to extract the `"text"` field from the response body,
then pass that string directly into your existing chat Blueprint as if the
player had typed the message.

### Minimal C++ helper to export a USoundWave to WAV

If you need to convert a `USoundWave*` to a WAV file on disk so that Blueprint
can POST it, add this helper to your project:

```cpp
// WavExporter.h
#pragma once
#include "Sound/SoundWave.h"
#include "Misc/Paths.h"
#include "HAL/FileManager.h"

static FString ExportSoundWaveToTempWav(USoundWave* Wave)
{
    if (!Wave) return FString();
    const FString TmpPath = FPaths::ProjectSavedDir() / TEXT("mic_capture.wav");
    // USoundWave stores raw PCM in RawData; write a minimal WAV header + data.
    TArray<uint8> RawPCM;
    Wave->RawData.GetCopy((void**)&RawPCM, true);
    // … write WAV header + RawPCM to TmpPath using IFileManager …
    return TmpPath;
}
```

A full, copy-paste implementation is beyond the scope of this README; several
community plugins (e.g. **RuntimeAudioImporter**) expose this functionality
directly to Blueprint with no C++ required.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'whisper'` | Package not installed | `pip install -r requirements.txt` |
| `FileNotFoundError: ffmpeg not found` | ffmpeg missing from PATH | Install ffmpeg and restart your shell |
| Server returns HTTP 500 | Audio file corrupt or unsupported format | Ensure the file is a valid WAV/OGG/MP3 |
| No microphone input on Linux | Wrong ALSA/PulseAudio device | Run `python -c "import sounddevice; print(sounddevice.query_devices())"` and set `--device` |
| UE5 Blueprint HTTP request times out | Server not running, or wrong port | Confirm server is running; check firewall |

---

## Security Notes

- By default the server only listens on `127.0.0.1` (localhost).  If you use
  `--host 0.0.0.0` to accept remote connections, ensure the port is firewalled
  to trusted hosts only.
- The server does **not** implement authentication.  For production use, place
  it behind a reverse proxy with TLS and API-key authentication.
- Uploaded audio files are written to a temporary directory and deleted
  immediately after transcription.
