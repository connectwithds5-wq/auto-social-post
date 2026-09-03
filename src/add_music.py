import os
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

VIDEO_FILE = os.path.join(ROOT, "output", "quote_reel.mp4")
MUSIC_FILE = os.path.join(
    ROOT,
    "assets",
    "music",
    "motivational_instrumental.mp3"
)
TEMP_FILE = os.path.join(
    ROOT,
    "output",
    "quote_reel_with_music.mp4"
)

if not os.path.exists(VIDEO_FILE):
    raise RuntimeError(f"Video not found: {VIDEO_FILE}")

if not os.path.exists(MUSIC_FILE):
    raise RuntimeError(f"Music not found: {MUSIC_FILE}")

print("Adding motivational instrumental music...")

subprocess.run([
    "ffmpeg",
    "-y",
    "-i", VIDEO_FILE,
    "-stream_loop", "-1",
    "-i", MUSIC_FILE,
    "-filter_complex",
    "[1:a]volume=0.18,"
    "afade=t=in:st=0:d=0.5,"
    "afade=t=out:st=9:d=1[a];"
    "[a]atrim=0:10[music]",
    "-map", "0:v:0",
    "-map", "[music]",
    "-c:v", "copy",
    "-c:a", "aac",
    "-b:a", "128k",
    "-shortest",
    "-movflags", "+faststart",
    TEMP_FILE
], check=True)

os.replace(TEMP_FILE, VIDEO_FILE)

print("Music added successfully!")
