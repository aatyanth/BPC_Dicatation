"""
local_transcribe.py
-------------------
Record audio from the local microphone and transcribe it using OpenAI Whisper.

This script is intended for direct use on the development machine.  It does NOT
require UE5 to be running.

Modes
-----
push-to-talk  (default)
    Press ENTER to start recording, press ENTER again to stop.
    The recording is then transcribed and printed to the console.

continuous
    The script records in a loop until you press Ctrl+C.  Each recording
    session is separated by pressing ENTER to stop and immediately starts a new
    recording after transcription.

Usage
-----
    python local_transcribe.py [--model MODEL] [--samplerate RATE]
                               [--channels CHANNELS] [--mode MODE]
                               [--output-file FILE]

    --model       Whisper model size: tiny | base | small | medium | large
                  (default: base)
    --samplerate  Microphone sample rate in Hz (default: 16000)
    --channels    Number of audio channels (default: 1 / mono)
    --mode        Recording mode: push-to-talk | continuous (default: push-to-talk)
    --output-file Optional path to save the final transcription as a plain-text file.

Examples
--------
    # Basic push-to-talk transcription:
    python local_transcribe.py

    # Use the more accurate 'small' model and save results to a file:
    python local_transcribe.py --model small --output-file transcript.txt

    # Continuous dictation loop:
    python local_transcribe.py --mode continuous
"""

import argparse
import os
import queue
import sys
import tempfile
import threading

import numpy as np
import sounddevice as sd
import soundfile as sf
import whisper


def record_until_enter(samplerate: int, channels: int) -> np.ndarray:
    """
    Record microphone audio in a background thread until the user presses ENTER.

    Returns
    -------
    np.ndarray
        Recorded PCM data, shape (n_samples, channels), dtype float32.
    """
    audio_queue: queue.Queue = queue.Queue()
    stop_event = threading.Event()

    def _callback(indata, frames, time_info, status):  # noqa: ARG001
        if status:
            print(f"[sounddevice warning] {status}", file=sys.stderr)
        audio_queue.put(indata.copy())

    print("  🎙  Recording … press ENTER to stop.")
    with sd.InputStream(
        samplerate=samplerate,
        channels=channels,
        dtype="float32",
        callback=_callback,
    ):
        # Wait for the user to press ENTER in a separate thread so the
        # audio callback can keep running on the main thread's stream.
        def _wait_for_enter():
            input()
            stop_event.set()

        t = threading.Thread(target=_wait_for_enter, daemon=True)
        t.start()
        stop_event.wait()

    # Drain the queue and concatenate all chunks.
    chunks = []
    while not audio_queue.empty():
        chunks.append(audio_queue.get_nowait())

    if not chunks:
        return np.zeros((0, channels), dtype=np.float32)

    return np.concatenate(chunks, axis=0)


def transcribe_audio(
    audio: np.ndarray,
    samplerate: int,
    model: whisper.Whisper,
) -> str:
    """
    Write *audio* to a temporary WAV file and return the Whisper transcription.

    Parameters
    ----------
    audio:
        PCM data from the microphone, shape (n_samples, channels), float32.
    samplerate:
        Sample rate used during recording.
    model:
        Pre-loaded Whisper model.

    Returns
    -------
    str
        Transcribed text, stripped of leading/trailing whitespace.
    """
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        sf.write(tmp_path, audio, samplerate)
        result = model.transcribe(tmp_path)
        return result["text"].strip()
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def run_push_to_talk(
    model: whisper.Whisper,
    samplerate: int,
    channels: int,
    output_file: str | None,
):
    """Single-shot push-to-talk recording and transcription."""
    print("\nPress ENTER to start recording.")
    input()

    audio = record_until_enter(samplerate, channels)
    if audio.shape[0] == 0:
        print("No audio was captured.")
        return

    print("  ⏳  Transcribing …")
    text = transcribe_audio(audio, samplerate, model)

    print(f"\n📝  Transcription:\n{text}\n")

    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print(f"Saved to '{output_file}'.")


def run_continuous(
    model: whisper.Whisper,
    samplerate: int,
    channels: int,
    output_file: str | None,
):
    """
    Continuous dictation loop.  Records and transcribes in a loop until the
    user presses Ctrl+C.
    """
    all_texts: list[str] = []
    print("\nContinuous mode — press Ctrl+C to stop.\n")
    print("Press ENTER to start the first recording.")
    input()

    try:
        while True:
            audio = record_until_enter(samplerate, channels)
            if audio.shape[0] == 0:
                print("No audio captured, ready for next recording.")
                input("Press ENTER to start recording.")
                continue

            print("  ⏳  Transcribing …")
            text = transcribe_audio(audio, samplerate, model)
            all_texts.append(text)
            print(f"\n📝  Transcription:\n{text}\n")

            print("Press ENTER to record again (or Ctrl+C to quit).")
            input()

    except KeyboardInterrupt:
        print("\nStopped.")

    if output_file and all_texts:
        combined = "\n".join(all_texts)
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(combined + "\n")
        print(f"All transcriptions saved to '{output_file}'.")


def main():
    parser = argparse.ArgumentParser(
        description="Record from local microphone and transcribe with Whisper"
    )
    parser.add_argument(
        "--model",
        default="base",
        choices=["tiny", "base", "small", "medium", "large"],
        help="Whisper model size (default: base).",
    )
    parser.add_argument(
        "--samplerate",
        type=int,
        default=16000,
        help="Microphone sample rate in Hz (default: 16000).",
    )
    parser.add_argument(
        "--channels",
        type=int,
        default=1,
        help="Number of audio channels, 1 = mono (default: 1).",
    )
    parser.add_argument(
        "--mode",
        choices=["push-to-talk", "continuous"],
        default="push-to-talk",
        help="Recording mode (default: push-to-talk).",
    )
    parser.add_argument(
        "--output-file",
        default=None,
        metavar="FILE",
        help="Optional path to write the transcription to.",
    )
    args = parser.parse_args()

    print(f"Loading Whisper model '{args.model}' … (this may take a moment)")
    model = whisper.load_model(args.model)
    print("Model loaded.\n")

    if args.mode == "push-to-talk":
        run_push_to_talk(model, args.samplerate, args.channels, args.output_file)
    else:
        run_continuous(model, args.samplerate, args.channels, args.output_file)


if __name__ == "__main__":
    main()
