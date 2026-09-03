import json
import os
import random
import subprocess
from PIL import Image, ImageDraw, ImageFont
from google import genai

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

QUOTES_FILE = os.path.join(ROOT, "content", "quotes.json")
OUTPUT_DIR = os.path.join(ROOT, "output")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "quote_reel.mp4")
METADATA_FILE = os.path.join(OUTPUT_DIR, "metadata.json")

WIDTH = 1080
HEIGHT = 1920
FPS = 30
DURATION = 10

os.makedirs(OUTPUT_DIR, exist_ok=True)

# -----------------------------
# Gemini AI
# -----------------------------

api_key = os.environ.get("GEMINI_API_KEY")

if not api_key:
    raise RuntimeError("GEMINI_API_KEY GitHub Secret is missing.")

client = genai.Client(api_key=api_key)

prompt = """
Create ONE original Hindi motivational quote for an Instagram Reel / YouTube Short.

Return ONLY valid JSON in this exact format:

{
  "quote": "short Hindi quote",
  "title": "YouTube Shorts SEO title",
  "caption": "Instagram caption with a natural call to action",
  "description": "YouTube description",
  "keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"],
  "hashtags": ["#hindiquotes", "#hindimotivation", "#motivation", "#reels", "#shorts"]
}

Rules:
- Quote must be original.
- Use simple, emotional Hindi.
- Quote should be short enough for a 10-second vertical video.
- Avoid copyrighted song lyrics.
- Do not make medical, financial or political claims.
- Keywords should be relevant to Hindi motivation and YouTube Shorts.
- Use 5 to 10 hashtags.
"""

response = client.models.generate_content(
    model="gemini-3.6-flash",
    contents=prompt
)

text = response.text.strip()

# Remove markdown code fences if Gemini adds them
text = text.replace("```json", "").replace("```", "").strip()

try:
    metadata = json.loads(text)
except json.JSONDecodeError:
    raise RuntimeError("Gemini returned invalid JSON:\n" + text)

quote = metadata["quote"]

with open(METADATA_FILE, "w", encoding="utf-8") as f:
    json.dump(metadata, f, ensure_ascii=False, indent=2)

print("AI content generated successfully.")
print("Quote:", quote)

# -----------------------------
# Video generation
# -----------------------------

background = Image.new("RGB", (WIDTH, HEIGHT), (18, 18, 24))
draw = ImageDraw.Draw(background)

bold_font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
regular_font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

try:
    quote_font = ImageFont.truetype(bold_font_path, 68)
    small_font = ImageFont.truetype(regular_font_path, 34)
except:
    quote_font = ImageFont.load_default()
    small_font = ImageFont.load_default()


def wrap_text(text, font, max_width):
    words = text.split()
    lines = []
    current = ""

    for word in words:
        test = current + (" " if current else "") + word
        bbox = draw.textbbox((0, 0), test, font=font)

        if bbox[2] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word

    if current:
        lines.append(current)

    return lines


lines = wrap_text(quote, quote_font, 900)

line_height = 100
total_height = len(lines) * line_height
start_y = (HEIGHT - total_height) // 2

frames_dir = os.path.join(OUTPUT_DIR, "frames")
os.makedirs(frames_dir, exist_ok=True)


def create_frame(path, progress):
    img = background.copy()
    d = ImageDraw.Draw(img)

    # Cinematic background
    for i in range(0, HEIGHT, 40):
        shade = int(18 + (i / HEIGHT) * 20)

        d.rectangle(
            [0, i, WIDTH, i + 40],
            fill=(shade, shade, min(40, shade + 8))
        )

    # Border
    d.rounded_rectangle(
        [70, 70, WIDTH - 70, HEIGHT - 70],
        radius=35,
        outline=(100, 100, 110),
        width=2
    )

    # Quote
    y = start_y

    for line in lines:
        bbox = d.textbbox((0, 0), line, font=quote_font)
        text_width = bbox[2] - bbox[0]
        x = (WIDTH - text_width) // 2

        # Shadow
        d.text(
            (x + 4, y + 4),
            line,
            font=quote_font,
            fill=(0, 0, 0)
        )

        # Main text
        d.text(
            (x, y),
            line,
            font=quote_font,
            fill=(245, 245, 245)
        )

        y += line_height

    # Branding
    branding = "Daily Motivation"

    bbox = d.textbbox(
        (0, 0),
        branding,
        font=small_font
    )

    d.text(
        (
            (WIDTH - (bbox[2] - bbox[0])) // 2,
            HEIGHT - 180
        ),
        branding,
        font=small_font,
        fill=(190, 190, 190)
    )

    # Progress bar
    progress_width = int((WIDTH - 140) * progress)

    d.rectangle(
        [
            70,
            HEIGHT - 90,
            70 + progress_width,
            HEIGHT - 82
        ],
        fill=(220, 220, 220)
    )

    img.save(path, quality=95)


total_frames = FPS * DURATION

for i in range(total_frames):

    progress = i / max(1, total_frames - 1)

    frame_path = os.path.join(
        frames_dir,
        f"frame_{i:04d}.jpg"
    )

    create_frame(
        frame_path,
        progress
    )


# -----------------------------
# FFmpeg MP4
# -----------------------------

subprocess.run(
    [
        "ffmpeg",
        "-y",
        "-framerate",
        str(FPS),
        "-i",
        os.path.join(
            frames_dir,
            "frame_%04d.jpg"
        ),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(FPS),
        "-movflags",
        "+faststart",
        OUTPUT_FILE
    ],
    check=True
)

print("")
print("================================")
print("VIDEO CREATED SUCCESSFULLY")
print("================================")
print("Video:", OUTPUT_FILE)
print("Metadata:", METADATA_FILE)
print("Title:", metadata["title"])
print("Hashtags:", " ".join(metadata["hashtags"]))
