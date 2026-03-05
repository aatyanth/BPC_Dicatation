import argparse
import json
import mimetypes
import os
import uuid
import urllib.error
import urllib.request


API_URL = "http://127.0.0.1:5000/transcribe"
AUDIO_FILE = "C:/UnrealProjects/cyberarch-core/Plugins/BPC_Dictation/BPC_Dicatation/BPC_Dictation_Test.mp3"


def post_transcribe(file_path: str) -> tuple[int, str]:
    payload = {"file": file_path}
    body = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        API_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        return 0, f"Request failed: {exc}"


def build_multipart_body(field_name: str, file_path: str) -> tuple[bytes, str]:
    boundary = f"----bpcdictation{uuid.uuid4().hex}"
    mime_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
    filename = os.path.basename(file_path)

    with open(file_path, "rb") as audio_file:
        file_bytes = audio_file.read()

    header = (
        f"--{boundary}\r\n"
        f"Content-Disposition: form-data; name=\"{field_name}\"; filename=\"{filename}\"\r\n"
        f"Content-Type: {mime_type}\r\n\r\n"
    ).encode("utf-8")
    footer = f"\r\n--{boundary}--\r\n".encode("utf-8")
    body = header + file_bytes + footer

    return body, boundary


def post_transcribe_upload(file_path: str) -> tuple[int, str]:
    body, boundary = build_multipart_body("audio", file_path)

    request = urllib.request.Request(
        API_URL,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        return 0, f"Request failed: {exc}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test the /transcribe Flask endpoint.")
    parser.add_argument("file", nargs="?", default=AUDIO_FILE, help="Path to audio file")
    parser.add_argument(
        "--mode",
        choices=["json", "upload"],
        default="upload",
        help="json: send {'file': path}, upload: send multipart file field 'audio'",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    if args.mode == "json":
        status_code, text = post_transcribe(args.file)
    else:
        status_code, text = post_transcribe_upload(args.file)

    print(f"Status: {status_code}")
    print("Response:")
    print(text)
