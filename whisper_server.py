"""
whisper_server.py
-----------------
A lightweight HTTP server that exposes OpenAI Whisper as a REST endpoint so
that Unreal Engine 5 Blueprints (or any HTTP client) can request speech-to-text
transcriptions without needing a Python environment inside UE5.

Endpoints
---------
POST /transcribe
    Accepts a multipart/form-data upload containing an audio file under the
    field name ``audio``.  The file can be in any format that ffmpeg supports
    (WAV, OGG, MP3, FLAC, …).  UE5's built-in microphone capture typically
    produces WAV files, which work directly.

    Returns JSON:
        {"text": "<transcription>"}

    On error:
        {"error": "<description>"}   with an appropriate HTTP status code.

GET /health
    Lightweight liveness check.  Returns {"status": "ok"}.

Usage
-----
    python whisper_server.py [--host HOST] [--port PORT] [--model MODEL]

    --host   Bind address (default: 127.0.0.1)
    --port   Listen port   (default: 8765)
    --model  Whisper model size: tiny | base | small | medium | large
             (default: base)

UE5 Blueprint Integration
--------------------------
1. Start this server on the machine running the UE5 editor (or any reachable host).
2. In your Blueprint, use the "HTTP" plugin nodes:
   a. Create an HTTP Request node.
   b. Set Verb = POST.
   c. Set URL = http://127.0.0.1:8765/transcribe
      (adjust host/port if the server is on a different machine).
   d. Use a "Set Content From File" or equivalent to attach the WAV file
      recorded by UE5's microphone capture.
   e. Add a header: Content-Type = multipart/form-data; boundary=<boundary>.
   f. On the response, parse the JSON body to extract the "text" field.
3. Feed the extracted text into your existing chat Blueprint as if the player
   had typed the message.

A ready-made UE5 Blueprint graph example is described in README.md.
"""

import argparse
import os
import tempfile
import threading

import whisper
from flask import Flask, jsonify, request

app = Flask(__name__)

# The Whisper model is loaded once at startup and reused for every request.
# Access is serialised with a lock because Whisper is not thread-safe.
_model = None
_model_lock = threading.Lock()


def get_model() -> whisper.Whisper:
    """Return the shared Whisper model, loading it on first call."""
    global _model
    if _model is None:
        raise RuntimeError("Whisper model has not been initialised yet.")
    return _model


@app.route("/health", methods=["GET"])
def health():
    """Liveness check endpoint."""
    return jsonify({"status": "ok"})


@app.route("/transcribe", methods=["POST"])
def transcribe():
    """
    Accept an audio file upload and return a Whisper transcription.

    Expected request
    ----------------
    Content-Type: multipart/form-data
    Field name  : audio
    """
    if "audio" not in request.files:
        return jsonify({"error": "No audio file provided. "
                        "POST the audio under the field name 'audio'."}), 400

    audio_file = request.files["audio"]
    if audio_file.filename == "":
        return jsonify({"error": "Audio filename is empty."}), 400

    # Save the uploaded bytes to a temporary file so Whisper can read it.
    suffix = _safe_extension(audio_file.filename)
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp_path = tmp.name
            audio_file.save(tmp_path)

        with _model_lock:
            model = get_model()
            result = model.transcribe(tmp_path)

        return jsonify({"text": result["text"].strip()})
    except Exception as exc:  # pylint: disable=broad-except
        return jsonify({"error": str(exc)}), 500
    finally:
        # Always clean up the temporary file.
        if "tmp_path" in locals() and os.path.exists(tmp_path):
            os.remove(tmp_path)


def _safe_extension(filename: str) -> str:
    """Return a safe file extension (with leading dot) from a filename."""
    _, ext = os.path.splitext(filename)
    # Allow only alphanumeric extensions to prevent path traversal.
    ext = ext.lstrip(".")
    if ext.isalnum():
        return f".{ext}"
    return ".wav"


def main():
    parser = argparse.ArgumentParser(
        description="Whisper HTTP server for UE5 Blueprint integration"
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind address (default: 127.0.0.1). "
             "Use 0.0.0.0 to accept remote connections.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Listen port (default: 8765).",
    )
    parser.add_argument(
        "--model",
        default="base",
        choices=["tiny", "base", "small", "medium", "large"],
        help="Whisper model size (default: base). "
             "Larger models are more accurate but slower and use more memory.",
    )
    args = parser.parse_args()

    global _model
    print(f"Loading Whisper model '{args.model}' … (this may take a moment)")
    _model = whisper.load_model(args.model)
    print(f"Model loaded. Starting server on http://{args.host}:{args.port}")

    app.run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
