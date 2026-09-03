import json
import os
import random
import subprocess
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

QUOTES_FILE = os.path.join(ROOT, "content", "quotes.json")
OUTPUT_DIR = os.path.join(ROOT, "output")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "quote_reel.mp4")

WIDTH = 1080
HEIGHT = 1920
FPS = 30
DURATION = 10

os.makedirs(OUTPUT_DIR, exist_ok=True)

with open(QUOTES_FILE, "r", encoding="utf-8") as f:
    quotes = json.load(f)

item = random.choice(quotes)
quote = item["quote"]

# Background
background = Image.new("RGB", (WIDTH, HEIGHT), (18, 18, 24))
draw = ImageDraw.Draw(background)

# Fonts
font_paths = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
]

regular_font = font_paths[0]
bold_font = font_paths[1]

# Try to use a larger font
try:
    quote_font = ImageFont.truetype(bold_font, 68)
    small_font = ImageFont.truetype(regular_font, 34)
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

# Center the quote
line_height = 100
total_height = len(lines) * line_height
start_y = (HEIGHT - total_height) // 2

def create_frame(path, progress):
    img = background.copy()
    d = ImageDraw.Draw(img)

    # Simple cinematic gradient-like layers
    for i in range(0, HEIGHT, 40):
        shade = int(18 + (i / HEIGHT) * 20)
        d.rectangle(
            [0, i, WIDTH, i + 40],
            fill=(shade, shade, min(40, shade + 8))
        )

    # Decorative lines
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

        d.text(
            (x, y),
            line,
            font=quote_font,
            fill=(245, 245, 245)
        )

        y += line_height

    # Branding
    branding = "Daily Motivation"
    bbox = d.textbbox((0, 0), branding, font=small_font)
    d.text(
        ((WIDTH - (bbox[2] - bbox[0])) // 2, HEIGHT - 180),
        branding,
        font=small_font,
        fill=(190, 190, 190)
    )

    # Progress line
    progress_width = int((WIDTH - 140) * progress)
    d.rectangle(
        [70, HEIGHT - 90, 70 + progress_width, HEIGHT - 82],
        fill=(220, 220, 220)
    )

    img.save(path, quality=95)

frames_dir = os.path.join(OUTPUT_DIR, "frames")
os.makedirs(frames_dir, exist_ok=True)

total_frames = FPS * DURATION

for i in range(total_frames):
    progress = i / max(1, total_frames - 1)
    frame_path = os.path.join(frames_dir, f"frame_{i:04d}.jpg")
    create_frame(frame_path, progress)

# Create MP4 with FFmpeg
subprocess.run([
    "ffmpeg",
    "-y",
    "-framerate", str(FPS),
    "-i", os.path.join(frames_dir, "frame_%04d.jpg"),
    "-c:v", "libx264",
    "-pix_fmt", "yuv420p",
    "-r", str(FPS),
    "-movflags", "+faststart",
    OUTPUT_FILE
], check=True)

print("Video created successfully:")
print(OUTPUT_FILE)
print("Quote:", quote)
