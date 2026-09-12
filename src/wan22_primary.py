import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from google import genai
from google.genai import types
from gradio_client import Client

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "output"
VIDEO = OUTPUT / "quote_reel.mp4"
METADATA = OUTPUT / "metadata.json"
SPACE = os.getenv("HF_WAN_SPACE", "zerogpu-aoti/wan2-2-fp8da-aoti")
HF_TOKEN = os.getenv("HF_TOKEN") or None
CLIP_SECONDS = 3.5
SCENE_COUNT = 3
FINAL_SECONDS = 10.0
STEPS = int(os.getenv("WAN_STEPS", "4"))
GUIDANCE = float(os.getenv("WAN_GUIDANCE", "1.0"))
GUIDANCE_2 = float(os.getenv("WAN_GUIDANCE_2", "3.0"))


def run(cmd):
    print("RUN:", " ".join(map(str, cmd)))
    subprocess.run(cmd, check=True)


def extract_video_path(result):
    if isinstance(result, dict):
        for key in ("video", "output", "file", "path"):
            value = result.get(key)
            if isinstance(value, str) and value:
                return value
    if isinstance(result, (tuple, list)):
        for item in result:
            try:
                return extract_video_path(item)
            except RuntimeError:
                pass
    if isinstance(result, str) and result:
        return result
    raise RuntimeError(f"No video path returned by Wan 2.2: {result!r}")


def make_metadata():
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is missing")
    client = genai.Client(api_key=key)
    prompt = '''Create ONE original motivational quote for RISE MODE and return ONLY valid JSON.\nStructure: {"quote":"...","title":"...","caption":"...","description":"...","keywords":["..."],"hashtags":["#..."]}.\nQuote: English only, powerful, emotional, original, maximum 18 words. Title/caption/description must suit a 10-second YouTube Short/Instagram Reel. Avoid copyrighted lyrics, medical claims, politics and financial advice.'''
    models = [os.getenv("GEMINI_MODEL", "gemini-3.6-flash"), os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.5-flash-lite")]
    last = None
    for model in dict.fromkeys(models):
        try:
            r = client.models.generate_content(model=model, contents=prompt, config=types.GenerateContentConfig(response_mime_type="application/json"))
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", (getattr(r, "text", "") or "").strip(), flags=re.I)
            data = json.loads(text)
            if data.get("quote"):
                data["quote"] = " ".join(str(data["quote"]).split()[:18])
                METADATA.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                return data
        except Exception as exc:
            last = exc
            print(f"Gemini metadata model failed: {model}: {exc}")
    raise RuntimeError(f"Gemini metadata generation failed: {last}")


def make_clip(client, quote, index):
    work = OUTPUT / "wan22"
    work.mkdir(parents=True, exist_ok=True)
    path = work / f"scene_{index + 1}.mp4"
    prompt = ("Premium cinematic photorealistic inspirational short film, vertical composition, "
              f"visual story expressing this motivational idea: {quote}. "
              f"Scene {index + 1}: show a distinct powerful visual progression, elegant camera movement, "
              "natural human motion, dramatic lighting, realistic materials, shallow depth of field, "
              "high-end commercial cinematography. No text, captions, letters, logos or watermark.")[:1500]
    negative = "text, subtitles, letters, logo, watermark, distorted face, extra limbs, duplicate people, flicker, jitter, low quality, blurry, flat illustration"
    print(f"WAN PRIMARY: scene {index + 1}/{SCENE_COUNT} — Wan 2.2 14B T2V")
    result = client.predict(prompt, negative, CLIP_SECONDS, GUIDANCE, GUIDANCE_2, STEPS, 9000 + index, False, api_name="/generate_video")
    source = Path(extract_video_path(result))
    if not source.is_file():
        raise FileNotFoundError(source)
    shutil.copy2(source, path)
    return path


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    if VIDEO.exists():
        VIDEO.unlink()
    data = make_metadata()
    client = Client(SPACE, token=HF_TOKEN) if HF_TOKEN else Client(SPACE)
    clips = [make_clip(client, data["quote"], i) for i in range(SCENE_COUNT)]
    concat = OUTPUT / "wan22_concat.txt"
    concat.write_text("\n".join(f"file '{p.resolve()}'" for p in clips), encoding="utf-8")
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-vf", "fps=30,scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1", "-t", str(FINAL_SECONDS), "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(VIDEO)])
    if not VIDEO.is_file() or VIDEO.stat().st_size < 50000:
        raise RuntimeError("Wan 2.2 produced an invalid video")
    run(["ffprobe", "-v", "error", "-show_entries", "format=duration,size", "-of", "default=noprint_wrappers=1", str(VIDEO)])
    print("WAN PRIMARY SUCCESS:", VIDEO)


if __name__ == "__main__":
    main()
