import json
import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIDEO_FILE = os.path.join(ROOT, "output", "quote_reel.mp4")
METADATA_FILE = os.path.join(ROOT, "output", "metadata.json")

SEO_KEYWORDS = [
    "motivation", "motivational quotes", "daily motivation", "success mindset",
    "positive mindset", "self improvement", "personal growth", "inspiration",
    "life quotes", "success quotes", "mindset", "discipline", "hard work",
    "confidence", "motivational video", "inspirational quotes", "rise mode"
]

SEO_HASHTAGS = [
    "#motivation", "#motivationalquotes", "#dailymotivation", "#successmindset",
    "#mindset", "#selfimprovement", "#inspiration", "#successquotes",
    "#discipline", "#personalgrowth", "#motivationdaily", "#shorts",
    "#youtubeshorts", "#risemode"
]


def load_credentials():
    client_id = os.environ.get("YOUTUBE_CLIENT_ID")
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET")
    refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN")

    missing = [
        name for name, value in {
            "YOUTUBE_CLIENT_ID": client_id,
            "YOUTUBE_CLIENT_SECRET": client_secret,
            "YOUTUBE_REFRESH_TOKEN": refresh_token,
        }.items() if not value
    ]

    if missing:
        raise RuntimeError(
            "Missing YouTube OAuth GitHub Secrets: " + ", ".join(missing)
        )

    credentials = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=SCOPES,
    )

    try:
        credentials.refresh(Request())
    except Exception as exc:
        raise RuntimeError(
            "YouTube OAuth refresh failed. Check that YOUTUBE_CLIENT_ID, "
            "YOUTUBE_CLIENT_SECRET and YOUTUBE_REFRESH_TOKEN belong to the "
            "same Google OAuth client and that the refresh token is valid."
        ) from exc

    if not credentials.valid:
        raise RuntimeError("YouTube OAuth credentials are invalid after refresh.")

    return credentials


def load_metadata():
    if not os.path.exists(METADATA_FILE):
        raise RuntimeError(f"Metadata file not found: {METADATA_FILE}")

    with open(METADATA_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def clean_tags(values):
    tags = []
    for value in values or []:
        tag = str(value).strip().lstrip("#")
        if tag and tag.lower() not in [x.lower() for x in tags]:
            tags.append(tag)
    return tags


def clean_hashtags(values):
    hashtags = []
    for value in values or []:
        tag = str(value).strip()
        if not tag:
            continue
        if not tag.startswith("#"):
            tag = "#" + tag
        if tag.lower() not in [x.lower() for x in hashtags]:
            hashtags.append(tag)
    return hashtags


def upload_video():
    if not os.path.exists(VIDEO_FILE):
        raise RuntimeError(f"Video not found: {VIDEO_FILE}")

    metadata = load_metadata()
    credentials = load_credentials()
    youtube = build("youtube", "v3", credentials=credentials)

    title = str(metadata.get("title", "Daily Motivation | Rise Mode")).strip()[:100]
    description = str(metadata.get("description", "")).strip()

    if not description:
        description = (
            "Believe in yourself. Keep going. Your future self will thank you.\n\n"
            "Daily motivation to help you build a stronger mindset, stay disciplined "
            "and keep moving forward."
        )

    description += """

🔥 RISE MODE — BUILD YOUR MINDSET

Follow for daily motivation, powerful quotes,
success mindset and self-improvement content.

💪 Stay focused.
🔥 Stay disciplined.
🚀 Keep rising.
"""

    metadata_hashtags = clean_hashtags(metadata.get("hashtags", []))
    all_hashtags = []
    for tag in metadata_hashtags + SEO_HASHTAGS:
        if tag.lower() not in [x.lower() for x in all_hashtags]:
            all_hashtags.append(tag)
    description += "\n" + " ".join(all_hashtags[:15])
    description = description[:5000]

    metadata_keywords = clean_tags(metadata.get("keywords", []))
    tags = []
    for tag in metadata_keywords + SEO_KEYWORDS:
        if tag.lower() not in [x.lower() for x in tags]:
            tags.append(tag)

    final_tags = []
    current_length = 0
    for tag in tags:
        extra_length = len(tag) + 1
        if current_length + extra_length > 480:
            break
        final_tags.append(tag)
        current_length += extra_length

    privacy = os.environ.get("YOUTUBE_PRIVACY_STATUS", "public").lower()
    if privacy not in {"public", "private", "unlisted"}:
        privacy = "public"

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": final_tags,
            "categoryId": "22",
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en",
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }

    print("================================")
    print("UPLOADING TO YOUTUBE")
    print("================================")
    print("Title:", title)
    print("Privacy:", privacy)
    print("SEO tags:", len(final_tags))
    print("Hashtags:", len(all_hashtags))

    media = MediaFileUpload(
        VIDEO_FILE,
        mimetype="video/mp4",
        resumable=True,
        chunksize=1024 * 1024,
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print("Upload progress:", int(status.progress() * 100), "%")

    video_id = response.get("id")
    if not video_id:
        raise RuntimeError("YouTube returned no video ID.")

    print("================================")
    print("YOUTUBE UPLOAD SUCCESSFUL")
    print("================================")
    print("Video ID:", video_id)
    print("URL:", f"https://www.youtube.com/watch?v={video_id}")
    print("SEO metadata added successfully.")
    print("================================")


if __name__ == "__main__":
    upload_video()
