# BPC Dictation — Whisper Speech-to-Text Integration for UE5

This repository provides Python scripts that add OpenAI Whisper-powered
speech-to-text capabilities to an Unreal Engine 5 project's chat system:

| Script | Purpose |
|---|---|
| `api_server.py` | Lightweight Flask HTTP server (port 5000) that transcribes audio by calling `script.py` as a subprocess |
| `script.py` | Core Whisper transcription helper; loads the `turbo` model, transcribes a file, and prints the result to stdout |
| `whisper_server.py` | Alternative HTTP server (port 8765) that loads Whisper in-process and serves the same REST API |
| `local_transcribe.py` | Standalone microphone → text tool for the developer machine |
| `test_api_client.py` | Command-line test client for the `/transcribe` endpoint of `api_server.py` |

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

## 1 — API Server (`api_server.py`) + Transcription Helper (`script.py`)

`api_server.py` is a Flask HTTP server that exposes a `/transcribe` endpoint on
**port 5000**.  For every request it delegates to `script.py` via a subprocess,
which loads the Whisper `turbo` model, transcribes the audio file, and returns
the text on stdout.  This design keeps the server process lightweight and
sidesteps Flask's threading constraints because each transcription runs in its
own isolated Python process.

### Start the server

```bash
# Binds to 127.0.0.1:5000
python api_server.py
```

### API Reference

#### `POST /transcribe`

Accepts audio in **either** of two forms:

| Method | Content-Type | Description |
|---|---|---|
| Multipart upload | `multipart/form-data` | Upload the audio under the field name `audio` |
| Raw bytes | any (e.g. `audio/wav`) | Send raw audio bytes directly in the request body |

**Success response (HTTP 200)**

```json
{ "text": "Hello, this is the transcribed text." }
```

**Error response (HTTP 400 / 500)**

```json
{ "error": "No audio data provided. Send multipart field 'audio' or raw wav bytes." }
```

### Quick test with curl

```bash
# Multipart upload
curl -X POST http://127.0.0.1:5000/transcribe \
     -F "audio=@recording.wav"

# Raw bytes
curl -X POST http://127.0.0.1:5000/transcribe \
     --data-binary @recording.wav \
     -H "Content-Type: audio/wav"
```

### How `script.py` works

`script.py` is called by `api_server.py` and is not meant to be invoked
directly in normal use, but you can run it standalone:

```bash
python script.py /path/to/audio.mp3
```

It loads the Whisper `turbo` model, transcribes the given file, and prints the
transcription to stdout.  `api_server.py` captures that output and returns it
as JSON.

> **Note:** The `turbo` model is a distilled large-v3 variant — it offers
> near-`large` accuracy at roughly 8× the speed of `large`.

---

## 2 — Alternative Whisper Server (`whisper_server.py`)

`whisper_server.py` is an alternative to `api_server.py`.  It loads the
Whisper model **once at startup** and keeps it in memory, so the first
transcription is slow (model load) but subsequent ones are faster.  Use this
server when you want lower per-request latency and are comfortable with the
higher memory footprint of a resident model.

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

## 3 — Local Transcription (`local_transcribe.py`)

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

## 4 — UE5 Blueprint Integration

The diagram below shows how the systems connect.  Either `api_server.py` (port
5000) or `whisper_server.py` (port 8765) can serve as the transcription backend.

```
  ┌─────────────────────────────┐         ┌──────────────────────────────────────┐
  │      UE5 Game (Blueprints)  │         │  api_server.py  (port 5000)          │
  │                             │  POST   │    └─► script.py (turbo model)       │
  │  MicrophoneCapture ──────► WAV ──────►│  /transcribe                         │
  │                             │  JSON   │                                      │
  │  Chat System ◄──── "text" ◄─┼─────────│  {"text": "…"}                      │
  └─────────────────────────────┘         └──────────────────────────────────────┘

                                   — or —

  ┌─────────────────────────────┐         ┌──────────────────────────────────────┐
  │      UE5 Game (Blueprints)  │         │  whisper_server.py  (port 8765)      │
  │                             │  POST   │    (model loaded in-process)         │
  │  MicrophoneCapture ──────► WAV ──────►│  /transcribe                         │
  │                             │  JSON   │                                      │
  │  Chat System ◄──── "text" ◄─┼─────────│  {"text": "…"}                      │
  └─────────────────────────────┘         └──────────────────────────────────────┘
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
                       URL:  http://127.0.0.1:5000/transcribe   ← api_server.py
                          or http://127.0.0.1:8765/transcribe   ← whisper_server.py
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

## 5 — Test Client (`test_api_client.py`)

`test_api_client.py` is a command-line utility for testing the `/transcribe`
endpoint of `api_server.py` (port 5000) from the host machine.  It does not
require a running UE5 instance.

```bash
# Upload an audio file using multipart/form-data (default)
python test_api_client.py /path/to/audio.mp3

# Send a JSON body containing the file path
python test_api_client.py /path/to/audio.mp3 --mode json

# Use the bundled test file (path is hard-coded in the script)
python test_api_client.py
```

| Mode | Description |
|---|---|
| `upload` (default) | Sends the file as a `multipart/form-data` upload in the `audio` field |
| `json` | Sends `{"file": "<path>"}` as a JSON body |

The script prints the HTTP status code and the raw response body, which makes
it easy to verify server behaviour without a browser or Postman.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'whisper'` | Package not installed | `pip install -r requirements.txt` |
| `FileNotFoundError: ffmpeg not found` | ffmpeg missing from PATH | Install ffmpeg and restart your shell |
| Server returns HTTP 500 | Audio file corrupt or unsupported format | Ensure the file is a valid WAV/OGG/MP3 |
| `api_server.py` returns HTTP 500 with `details` field | `script.py` crashed | Check the `details` field in the response for the Python traceback |
| No microphone input on Linux | Wrong ALSA/PulseAudio device | Run `python -c "import sounddevice; print(sounddevice.query_devices())"` and set `--device` |
| UE5 Blueprint HTTP request times out | Server not running, or wrong port | Confirm server is running on the correct port (5000 for `api_server.py`, 8765 for `whisper_server.py`); check firewall |

---

## Security Notes

- Both servers (`api_server.py` and `whisper_server.py`) only listen on
  `127.0.0.1` (localhost) by default.  `whisper_server.py` accepts a
  `--host 0.0.0.0` flag to allow remote connections; if you use it, ensure the
  port is firewalled to trusted hosts only.
- Neither server implements authentication.  For production use, place the
  server behind a reverse proxy with TLS and API-key authentication.
- Uploaded audio files are written to a temporary directory and deleted
  immediately after transcription.
