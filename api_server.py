from flask import Flask, request, jsonify
from pathlib import Path
import os
import subprocess
import sys
import tempfile

app = Flask(__name__)

def run_whisper(audio_path: str) -> tuple[str, str, int]:
    result = subprocess.run(
        [sys.executable, "script.py", audio_path],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip(), result.stderr.strip(), result.returncode


@app.route("/transcribe", methods=["POST"])
def transcribe():
    temp_audio_path = None

    try:
        if "audio" in request.files:
            uploaded_file = request.files["audio"]
            if uploaded_file.filename == "":
                return jsonify({"error": "Uploaded filename is empty."}), 400

            suffix = Path(uploaded_file.filename).suffix or ".wav"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, prefix="bpc_dictation_") as temp_file:
                uploaded_file.save(temp_file)
                temp_audio_path = temp_file.name

            audio_path = temp_audio_path
        else:
            # Support raw audio bytes in request body (for UE/HTTP clients sending wav directly).
            audio_bytes = request.get_data(cache=False)
            if not audio_bytes:
                return jsonify({"error": "No audio data provided. Send multipart field 'audio' or raw wav bytes."}), 400

            suffix = ".wav"
            content_type = (request.content_type or "").lower()
            if "mpeg" in content_type or "mp3" in content_type:
                suffix = ".mp3"
            elif "ogg" in content_type:
                suffix = ".ogg"

            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, prefix="bpc_dictation_") as temp_file:
                temp_file.write(audio_bytes)
                temp_audio_path = temp_file.name

            audio_path = temp_audio_path

        transcript, stderr, return_code = run_whisper(audio_path)
        if return_code != 0:
            return jsonify({"error": "Transcription failed.", "details": stderr}), 500

        return jsonify({"text": transcript})
    finally:
        # Uploaded files are copied to a temp file so Whisper can read from disk.
        if temp_audio_path and os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)

if __name__ == '__main__':

    app.run(host='127.0.0.1', port=5000)