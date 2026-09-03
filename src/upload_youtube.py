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


# ==========================================================
# SEO DEFAULTS
# ==========================================================

SEO_KEYWORDS = [
    "motivation",
    "motivational quotes",
    "daily motivation",
    "success mindset",
    "positive mindset",
    "self improvement",
    "personal growth",
    "inspiration",
    "life quotes",
    "success quotes",
    "mindset",
    "discipline",
    "hard work",
    "confidence",
    "motivational video",
    "inspirational quotes",
    "rise mode"
]

SEO_HASHTAGS = [
    "#motivation",
    "#motivationalquotes",
    "#dailymotivation",
    "#successmindset",
    "#mindset",
    "#selfimprovement",
    "#inspiration",
    "#successquotes",
    "#discipline",
    "#personalgrowth",
    "#motivationdaily",
    "#shorts",
    "#youtubeshorts",
    "#risemode"
]


def load_credentials():

    raw = os.environ.get("YOUTUBE_OAUTH_JSON")

    if not raw:
        raise RuntimeError(
            "YOUTUBE_OAUTH_JSON GitHub Secret is missing."
        )

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "YOUTUBE_OAUTH_JSON is not valid JSON."
        ) from exc

    if "refresh_token" not in data:
        raise RuntimeError(
            "YOUTUBE_OAUTH_JSON has no refresh_token."
        )

    credentials = Credentials.from_authorized_user_info(
        data,
        SCOPES
    )

    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())

    if not credentials.valid:
        raise RuntimeError(
            "YouTube OAuth credentials are invalid."
        )

    return credentials


def load_metadata():

    if not os.path.exists(METADATA_FILE):
        raise RuntimeError(
            f"Metadata file not found: {METADATA_FILE}"
        )

    with open(
        METADATA_FILE,
        "r",
        encoding="utf-8"
    ) as file:
        return json.load(file)


def clean_tags(values):

    tags = []

    for value in values or []:

        tag = str(value).strip().lstrip("#")

        if tag and tag not in tags:
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
        raise RuntimeError(
            f"Video not found: {VIDEO_FILE}"
        )

    metadata = load_metadata()

    credentials = load_credentials()

    youtube = build(
        "youtube",
        "v3",
        credentials=credentials
    )

    # ======================================================
    # TITLE
    # ======================================================

    title = str(
        metadata.get(
            "title",
            "Daily Motivation | Rise Mode"
        )
    ).strip()

    title = title[:100]

    # ======================================================
    # DESCRIPTION
    # ======================================================

    description = str(
        metadata.get(
            "description",
            ""
        )
    ).strip()

    if not description:

        description = (
            "Believe in yourself. Keep going. "
            "Your future self will thank you.\n\n"
            "Daily motivation to help you build a stronger "
            "mindset, stay disciplined and keep moving forward."
        )

    # Add SEO CTA

    seo_footer = """

🔥 RISE MODE — BUILD YOUR MINDSET

Follow for daily motivation, powerful quotes,
success mindset and self-improvement content.

💪 Stay focused.
🔥 Stay disciplined.
🚀 Keep rising.

"""

    description += seo_footer

    # ======================================================
    # HASHTAGS
    # ======================================================

    metadata_hashtags = clean_hashtags(
        metadata.get(
            "hashtags",
            []
        )
    )

    all_hashtags = []

    for tag in metadata_hashtags + SEO_HASHTAGS:

        if tag.lower() not in [
            x.lower() for x in all_hashtags
        ]:
            all_hashtags.append(tag)

    hashtag_text = " ".join(all_hashtags[:15])

    description += "\n" + hashtag_text

    # YouTube description limit
    description = description[:5000]

    # ======================================================
    # KEYWORDS / TAGS
    # ======================================================

    metadata_keywords = clean_tags(
        metadata.get(
            "keywords",
            []
        )
    )

    tags = []

    for tag in metadata_keywords + SEO_KEYWORDS:

        if tag.lower() not in [
            x.lower() for x in tags
        ]:
            tags.append(tag)

    # YouTube allows max 500 characters for tags
    final_tags = []

    current_length = 0

    for tag in tags:

        extra_length = len(tag) + 1

        if current_length + extra_length > 480:
            break

        final_tags.append(tag)
        current_length += extra_length

    # ======================================================
    # PRIVACY
    # ======================================================

    privacy = os.environ.get(
        "YOUTUBE_PRIVACY_STATUS",
        "public"
    ).lower()

    if privacy not in {
        "public",
        "private",
        "unlisted"
    }:
        privacy = "public"

    # ======================================================
    # YOUTUBE BODY
    # ======================================================

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": final_tags,
            "categoryId": "22",
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en"
        },

        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False
        }
    }

    # ======================================================
    # LOG
    # ======================================================

    print("================================")
    print("UPLOADING TO YOUTUBE")
    print("================================")

    print("Title:", title)
    print("Privacy:", privacy)
    print("SEO tags:", len(final_tags))
    print("Hashtags:", len(all_hashtags))

    # ======================================================
    # VIDEO UPLOAD
    # ======================================================

    media = MediaFileUpload(
        VIDEO_FILE,
        mimetype="video/mp4",
        resumable=True,
        chunksize=1024 * 1024
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media
    )

    response = None

    while response is None:

        status, response = request.next_chunk()

        if status:

            progress = int(
                status.progress() * 100
            )

            print(
                "Upload progress:",
                progress,
                "%"
            )

    # ======================================================
    # SUCCESS
    # ======================================================

    video_id = response.get("id")

    if not video_id:
        raise RuntimeError(
            "YouTube returned no video ID."
        )

    print("")
    print("================================")
    print("YOUTUBE UPLOAD SUCCESSFUL")
    print("================================")
    print("Video ID:", video_id)
    print(
        "URL:",
        f"https://www.youtube.com/watch?v={video_id}"
    )
    print("")
    print("SEO metadata added successfully.")
    print("================================")


if __name__ == "__main__":
    upload_video()
