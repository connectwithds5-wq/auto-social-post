"""
AI Content Strategy V1
Collects public YouTube performance for videos uploaded by Auto Social Post,
keeps a local history file in the repo, and asks Gemini for next-content strategy.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from google import genai
from google.genai import types

ROOT = Path(__file__).resolve().parents[1]
HISTORY_FILE = ROOT / "strategy_history.json"
STRATEGY_FILE = ROOT / "strategy.json"
CHANNEL_ID = os.environ.get("YOUTUBE_CHANNEL_ID", "").strip()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash").strip()

MAX_VIDEOS = 50


def load_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path, data):
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def youtube_public_data(video_ids):
    # Uses the public Data API endpoint through requests.
    # No OAuth token is needed for public statistics.
    import requests

    api_key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("YOUTUBE_API_KEY GitHub Secret is missing.")

    ids = ",".join(video_ids[:50])
    url = "https://www.googleapis.com/youtube/v3/videos"
    params = {
        "part": "snippet,statistics,contentDetails",
        "id": ids,
        "key": api_key,
    }
    r = requests.get(url, params=params, timeout=30)
    if not r.ok:
        raise RuntimeError(f"YouTube API {r.status_code}: {r.text[:500]}")
    return r.json().get("items", [])


def discover_video_ids():
    import requests

    api_key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("YOUTUBE_API_KEY GitHub Secret is missing.")

    if not CHANNEL_ID:
        raise RuntimeError("YOUTUBE_CHANNEL_ID GitHub Variable is missing.")

    # Uploads playlist is obtained from the channel resource.
    r = requests.get(
        "https://www.googleapis.com/youtube/v3/channels",
        params={
            "part": "contentDetails",
            "id": CHANNEL_ID,
            "key": api_key,
        },
        timeout=30,
    )
    if not r.ok:
        raise RuntimeError(f"YouTube channel API {r.status_code}: {r.text[:500]}")

    items = r.json().get("items", [])
    if not items:
        raise RuntimeError("YouTube channel not found. Check YOUTUBE_CHANNEL_ID.")

    uploads = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]

    r = requests.get(
        "https://www.googleapis.com/youtube/v3/playlistItems",
        params={
            "part": "contentDetails",
            "playlistId": uploads,
            "maxResults": MAX_VIDEOS,
            "key": api_key,
        },
        timeout=30,
    )
    if not r.ok:
        raise RuntimeError(f"YouTube playlist API {r.status_code}: {r.text[:500]}")

    return [
        x["contentDetails"]["videoId"]
        for x in r.json().get("items", [])
        if x.get("contentDetails", {}).get("videoId")
    ]


def normalize_video(item):
    s = item.get("statistics", {})
    sn = item.get("snippet", {})
    return {
        "video_id": item.get("id"),
        "title": sn.get("title", ""),
        "description": sn.get("description", "")[:1200],
        "published_at": sn.get("publishedAt"),
        "channel_title": sn.get("channelTitle", ""),
        "category_id": sn.get("categoryId"),
        "duration": item.get("contentDetails", {}).get("duration"),
        "views": int(s.get("viewCount", 0)),
        "likes": int(s.get("likeCount", 0)),
        "comments": int(s.get("commentCount", 0)),
    }


def build_prompt(videos):
    compact = []
    for v in videos:
        compact.append({
            "title": v["title"],
            "published_at": v["published_at"],
            "views": v["views"],
            "likes": v["likes"],
            "comments": v["comments"],
        })

    return f"""
You are the content strategist for RISE MODE, a motivational short-video brand.

Analyze ONLY the supplied YouTube performance data. Do not invent metrics.

Data:
{json.dumps(compact, ensure_ascii=False, indent=2)}

Create an actionable next-content strategy.

Rules:
- Identify patterns from the supplied data.
- Do not claim watch time or retention because those metrics are not supplied.
- Prefer repeatable themes, hooks, title patterns and publishing-time patterns supported by the data.
- Do not recommend simply copying existing quotes.
- Recommend fresh variations.
- If the dataset is too small for a strong conclusion, say so.
- Give confidence as low/medium/high.
- Keep recommendations practical for 10-second motivational Shorts.

Return ONLY valid JSON with exactly:
{{
  "generated_at": "",
  "overall_summary": "",
  "confidence": "low|medium|high",
  "what_is_working": [
    {{"pattern":"","evidence":"","action":""}}
  ],
  "what_to_improve": [
    {{"pattern":"","evidence":"","action":""}}
  ],
  "best_posting_windows": [
    {{"window":"","reason":"","confidence":"low|medium|high"}}
  ],
  "next_best_topics": [
    {{"priority":1,"topic":"","hook":"","format":"","reason":"","confidence":"low|medium|high"}}
  ],
  "avoid_or_limit": [
    {{"item":"","reason":""}}
  ]
}}
"""


def main():
    history = load_json(HISTORY_FILE, {"videos": []})
    existing = {x.get("video_id"): x for x in history.get("videos", [])}

    ids = discover_video_ids()
    if not ids:
        raise RuntimeError("No YouTube videos found.")

    items = youtube_public_data(ids)

    for item in items:
        v = normalize_video(item)
        existing[v["video_id"]] = v

    videos = list(existing.values())
    videos.sort(key=lambda x: x.get("published_at") or "", reverse=True)
    videos = videos[:MAX_VIDEOS]

    history = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "videos": videos,
    }
    save_json(HISTORY_FILE, history)

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY GitHub Secret is missing.")

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=build_prompt(videos),
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )

    text = response.text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]

    strategy = json.loads(text.strip())
    strategy["generated_at"] = datetime.now(timezone.utc).isoformat()
    strategy["data_points"] = len(videos)

    save_json(STRATEGY_FILE, strategy)

    print("AI CONTENT STRATEGY UPDATED")
    print("Videos analyzed:", len(videos))
    print("Strategy:", STRATEGY_FILE)


if __name__ == "__main__":
    main()
