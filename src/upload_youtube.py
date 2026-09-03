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
            "YOUTUBE_OAUTH_JSON has no refresh_token. "
            "You need to complete YouTube OAuth authorization first."
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

        if tag:
            tags.append(tag)

    return tags[:30]


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

    title = str(
        metadata.get(
            "title",
            "Daily Motivation"
        )
    )[:100]

    description = str(
        metadata.get(
            "description",
            ""
        )
    )

    hashtags = " ".join(
        metadata.get(
            "hashtags",
            []
        )
    )

    if hashtags:
        description = (
            description
            + "\n\n"
            + hashtags
        )[:5000]

    tags = clean_tags(
        metadata.get(
            "keywords",
            []
        )
    )

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

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": "22",
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en"
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False
        }
    }

    print("Uploading video to YouTube...")
    print("Title:", title)
    print("Privacy:", privacy)

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
            print(
                "Upload progress:",
                int(status.progress() * 100),
                "%"
            )

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


if __name__ == "__main__":
    upload_video()
