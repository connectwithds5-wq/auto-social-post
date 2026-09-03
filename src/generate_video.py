import json
import os
import random
import subprocess
import time

from PIL import Image, ImageDraw, ImageFont
from google import genai


# ============================================================
# SETTINGS
# ============================================================

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

OUTPUT_DIR = os.path.join(ROOT, "output")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "quote_reel.mp4")
METADATA_FILE = os.path.join(OUTPUT_DIR, "metadata.json")
FRAMES_DIR = os.path.join(OUTPUT_DIR, "frames")

WIDTH = 1080
HEIGHT = 1920
FPS = 30
DURATION = 10

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(FRAMES_DIR, exist_ok=True)


# ============================================================
# GEMINI AI
# ============================================================

api_key = os.environ.get("GEMINI_API_KEY")

if not api_key:
    raise RuntimeError("GEMINI_API_KEY GitHub Secret is missing.")

client = genai.Client(api_key=api_key)

prompt = """
Create ONE original motivational quote for a premium Instagram Reel
and YouTube Short.

IMPORTANT:
- Write everything in ENGLISH ONLY.
- Do NOT use Hindi.
- Do NOT use emojis inside the quote.
- Quote must be original.
- Quote must be powerful, emotional and inspirational.
- Maximum 18 words.
- Suitable for a 10-second vertical motivational video.
- Avoid copyrighted lyrics.
- Avoid medical, political or financial claims.

Return ONLY valid JSON in exactly this format:

{
  "quote": "Your original motivational quote here",
  "title": "SEO optimized YouTube Shorts title",
  "caption": "Short Instagram caption with natural call to action",
  "description": "SEO optimized YouTube Shorts description",
  "keywords": [
    "motivational quotes",
    "daily motivation",
    "success mindset",
    "self improvement",
    "inspiration"
  ],
  "hashtags": [
    "#motivation",
    "#motivationalquotes",
    "#mindset",
    "#success",
    "#selfimprovement",
    "#inspiration",
    "#reels",
    "#shorts"
  ]
}
"""


# ============================================================
# GEMINI RETRY
# ============================================================

model_name = os.environ.get(
    "GEMINI_MODEL",
    "gemini-3.6-flash"
)

max_retries = 5
response = None

for attempt in range(max_retries):

    try:

        print(
            f"Gemini API attempt "
            f"{attempt + 1}/{max_retries}..."
        )

        response = client.models.generate_content(
            model=model_name,
            contents=prompt
        )

        print("Gemini API success!")
        break

    except Exception as e:

        print("Gemini API error:")
        print(str(e))

        if attempt == max_retries - 1:
            raise RuntimeError(
                "Gemini API failed after all retries."
            ) from e

        wait_time = 15 * (attempt + 1)

        print(
            f"Waiting {wait_time} seconds before retry..."
        )

        time.sleep(wait_time)


if response is None:
    raise RuntimeError("No response received from Gemini.")


# ============================================================
# PARSE JSON
# ============================================================

text = response.text.strip()

text = (
    text
    .replace("```json", "")
    .replace("```", "")
    .strip()
)

try:

    metadata = json.loads(text)

except json.JSONDecodeError:

    raise RuntimeError(
        "Gemini returned invalid JSON:\n" + text
    )


required_fields = [
    "quote",
    "title",
    "caption",
    "description",
    "keywords",
    "hashtags"
]

for field in required_fields:

    if field not in metadata:
        raise RuntimeError(
            f"Gemini response missing field: {field}"
        )


quote = str(metadata["quote"]).strip()


# ============================================================
# SAVE METADATA
# ============================================================

with open(
    METADATA_FILE,
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        metadata,
        f,
        ensure_ascii=False,
        indent=2
    )


print("")
print("AI CONTENT GENERATED")
print("---------------------")
print("Quote:", quote)
print("Title:", metadata["title"])


# ============================================================
# FONTS
# ============================================================

FONT_BOLD = (
    "/usr/share/fonts/truetype/dejavu/"
    "DejaVuSans-Bold.ttf"
)

FONT_REGULAR = (
    "/usr/share/fonts/truetype/dejavu/"
    "DejaVuSans.ttf"
)


def load_font(path, size):

    try:
        return ImageFont.truetype(
            path,
            size
        )

    except Exception:

        return ImageFont.load_default()


QUOTE_FONT = load_font(
    FONT_BOLD,
    72
)

SMALL_FONT = load_font(
    FONT_REGULAR,
    30
)

BRAND_FONT = load_font(
    FONT_BOLD,
    34
)

SMALL_BOLD_FONT = load_font(
    FONT_BOLD,
    26
)


# ============================================================
# TEXT WRAPPING
# ============================================================

def wrap_text(text, font, max_width):

    words = text.split()

    lines = []
    current = ""

    dummy = Image.new(
        "RGB",
        (WIDTH, HEIGHT)
    )

    draw = ImageDraw.Draw(dummy)

    for word in words:

        test = (
            current
            + (" " if current else "")
            + word
        )

        bbox = draw.textbbox(
            (0, 0),
            test,
            font=font
        )

        text_width = bbox[2] - bbox[0]

        if text_width <= max_width:

            current = test

        else:

            if current:
                lines.append(current)

            current = word

    if current:
        lines.append(current)

    return lines


quote_lines = wrap_text(
    quote,
    QUOTE_FONT,
    820
)


# ============================================================
# RANDOM PARTICLES
# ============================================================

random.seed(42)

particles = []

for _ in range(70):

    particles.append(
        {
            "x": random.randint(40, WIDTH - 40),
            "y": random.randint(40, HEIGHT - 40),
            "r": random.randint(2, 6),
            "speed": random.uniform(0.2, 1.0),
            "phase": random.uniform(0, 6.28)
        }
    )


# ============================================================
# BACKGROUND
# ============================================================

def create_background():

    img = Image.new(
        "RGB",
        (WIDTH, HEIGHT)
    )

    pixels = img.load()

    for y in range(HEIGHT):

        vertical = y / HEIGHT

        for x in range(WIDTH):

            horizontal = x / WIDTH

            r = int(
                10
                + vertical * 12
                + horizontal * 5
            )

            g = int(
                12
                + vertical * 10
            )

            b = int(
                22
                + vertical * 18
                + horizontal * 10
            )

            pixels[x, y] = (
                r,
                g,
                b
            )

    return img


BACKGROUND = create_background()


# ============================================================
# FRAME CREATION
# ============================================================

def create_frame(frame_number):

    progress = (
        frame_number
        / max(
            1,
            FPS * DURATION - 1
        )
    )

    img = BACKGROUND.copy()

    draw = ImageDraw.Draw(img)

    # --------------------------------------------------------
    # TOP LABEL
    # --------------------------------------------------------

    label = "DAILY MOTIVATION"

    bbox = draw.textbbox(
        (0, 0),
        label,
        font=SMALL_BOLD_FONT
    )

    label_width = bbox[2] - bbox[0]

    draw.text(
        (
            (WIDTH - label_width) // 2,
            150
        ),
        label,
        font=SMALL_BOLD_FONT,
        fill=(220, 190, 110)
    )


    # --------------------------------------------------------
    # OUTER CANVA STYLE CARD
    # --------------------------------------------------------

    card_left = 65
    card_top = 230
    card_right = WIDTH - 65
    card_bottom = HEIGHT - 300

    # Shadow
    draw.rounded_rectangle(
        [
            card_left + 8,
            card_top + 12,
            card_right + 8,
            card_bottom + 12
        ],
        radius=55,
        fill=(5, 6, 12)
    )

    # Main card
    draw.rounded_rectangle(
        [
            card_left,
            card_top,
            card_right,
            card_bottom
        ],
        radius=55,
        fill=(24, 25, 38),
        outline=(90, 92, 110),
        width=3
    )


    # --------------------------------------------------------
    # INNER ACCENT LINE
    # --------------------------------------------------------

    draw.rounded_rectangle(
        [
            card_left + 18,
            card_top + 18,
            card_right - 18,
            card_bottom - 18
        ],
        radius=45,
        outline=(65, 67, 85),
        width=2
    )


    # --------------------------------------------------------
    # DECORATIVE TOP LINE
    # --------------------------------------------------------

    line_width = 120

    center_x = WIDTH // 2

    draw.rounded_rectangle(
        [
            center_x - line_width // 2,
            card_top + 75,
            center_x + line_width // 2,
            card_top + 82
        ],
        radius=4,
        fill=(220, 190, 110)
    )


    # --------------------------------------------------------
    # QUOTE
    # --------------------------------------------------------

    line_height = 105

    total_height = (
        len(quote_lines)
        * line_height
    )

    quote_start_y = (
        (card_top + card_bottom)
        // 2
        - total_height // 2
    )


    y = quote_start_y

    for index, line in enumerate(quote_lines):

        bbox = draw.textbbox(
            (0, 0),
            line,
            font=QUOTE_FONT
        )

        text_width = (
            bbox[2]
            - bbox[0]
        )

        x = (
            WIDTH
            - text_width
        ) // 2


        # Soft shadow
        draw.text(
            (
                x + 5,
                y + 7
            ),
            line,
            font=QUOTE_FONT,
            fill=(5, 5, 10)
        )


        # Main text
        draw.text(
            (
                x,
                y
            ),
            line,
            font=QUOTE_FONT,
            fill=(245, 245, 248)
        )


        y += line_height


    # --------------------------------------------------------
    # SMALL QUOTE MARK
    # --------------------------------------------------------

    quote_mark_font = load_font(
        FONT_BOLD,
        110
    )

    draw.text(
        (
            card_left + 55,
            card_top + 35
        ),
        "“",
        font=quote_mark_font,
        fill=(220, 190, 110)
    )


    # --------------------------------------------------------
    # BRANDING
    # --------------------------------------------------------

    brand = "Daily Motivation"

    bbox = draw.textbbox(
        (0, 0),
        brand,
        font=BRAND_FONT
    )

    brand_width = (
        bbox[2]
        - bbox[0]
    )

    draw.text(
        (
            (WIDTH - brand_width) // 2,
            HEIGHT - 220
        ),
        brand,
        font=BRAND_FONT,
        fill=(220, 220, 225)
    )


    # --------------------------------------------------------
    # FOLLOW TEXT
    # --------------------------------------------------------

    follow = "FOLLOW FOR DAILY INSPIRATION"

    bbox = draw.textbbox(
        (0, 0),
        follow,
        font=SMALL_FONT
    )

    follow_width = (
        bbox[2]
        - bbox[0]
    )

    draw.text(
        (
            (WIDTH - follow_width) // 2,
            HEIGHT - 165
        ),
        follow,
        font=SMALL_FONT,
        fill=(150, 152, 165)
    )


    # --------------------------------------------------------
    # FLOATING PARTICLES
    # --------------------------------------------------------

    for particle in particles:

        px = particle["x"]

        py = (
            particle["y"]
            - frame_number
            * particle["speed"]
        ) % HEIGHT

        radius = particle["r"]

        draw.ellipse(
            [
                px - radius,
                py - radius,
                px + radius,
                py + radius
            ],
            fill=(80, 82, 105)
        )


    # --------------------------------------------------------
    # PROGRESS BAR
    # --------------------------------------------------------

    bar_left = 70
    bar_right = WIDTH - 70
    bar_y = HEIGHT - 85

    draw.rounded_rectangle(
        [
            bar_left,
            bar_y,
            bar_right,
            bar_y + 7
        ],
        radius=4,
        fill=(55, 57, 70)
    )

    progress_right = (
        bar_left
        + int(
            (bar_right - bar_left)
            * progress
        )
    )

    draw.rounded_rectangle(
        [
            bar_left,
            bar_y,
            max(
                bar_left + 5,
                progress_right
            ),
            bar_y + 7
        ],
        radius=4,
        fill=(220, 190, 110)
    )


    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    path = os.path.join(
        FRAMES_DIR,
        f"frame_{frame_number:04d}.jpg"
    )

    img.save(
        path,
        "JPEG",
        quality=95
    )


# ============================================================
# GENERATE FRAMES
# ============================================================

total_frames = FPS * DURATION

print("")
print("Generating video frames...")

for frame_number in range(total_frames):

    create_frame(
        frame_number
    )

    if frame_number % FPS == 0:

        print(
            f"Progress: "
            f"{frame_number // FPS}/{DURATION} seconds"
        )


# ============================================================
# CREATE MP4 WITH FFMPEG
# ============================================================

print("")
print("Encoding MP4 video...")

subprocess.run(
    [
        "ffmpeg",
        "-y",

        "-framerate",
        str(FPS),

        "-i",
        os.path.join(
            FRAMES_DIR,
            "frame_%04d.jpg"
        ),

        "-c:v",
        "libx264",

        "-preset",
        "medium",

        "-crf",
        "20",

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


# ============================================================
# FINAL OUTPUT
# ============================================================

print("")
print("========================================")
print("       VIDEO CREATED SUCCESSFULLY")
print("========================================")
print("")
print("VIDEO:")
print(OUTPUT_FILE)
print("")
print("METADATA:")
print(METADATA_FILE)
print("")
print("TITLE:")
print(metadata["title"])
print("")
print("HASHTAGS:")
print(
    " ".join(
        metadata["hashtags"]
    )
)
print("")
print("========================================")
