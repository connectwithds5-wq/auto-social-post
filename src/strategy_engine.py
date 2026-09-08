"""
AI Content Strategy V2
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
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def youtube_public_data(video_ids):
    import requests
    api_key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("YOUTUBE_API_KEY GitHub Secret is missing.")
    ids = ",".join(video_ids[:50])
    r = requests.get("https://www.googleapis.com/youtube/v3/videos", params={"part": "snippet,statistics,contentDetails", "id": ids, "key": api_key}, timeout=30)
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
    r = requests.get("https://www.googleapis.com/youtube/v3/channels", params={"part": "contentDetails", "id": CHANNEL_ID, "key": api_key}, timeout=30)
    if not r.ok:
        raise RuntimeError(f"YouTube channel API {r.status_code}: {r.text[:500]}")
    items = r.json().get("items", [])
    if not items:
        raise RuntimeError("YouTube channel not found. Check YOUTUBE_CHANNEL_ID.")
    uploads = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    r = requests.get("https://www.googleapis.com/youtube/v3/playlistItems", params={"part": "contentDetails", "playlistId": uploads, "maxResults": MAX_VIDEOS, "key": api_key}, timeout=30)
    if not r.ok:
        raise RuntimeError(f"YouTube playlist API {r.status_code}: {r.text[:500]}")
    return [x["contentDetails"]["videoId"] for x in r.json().get("items", []) if x.get("contentDetails", {}).get("videoId")]


def normalize_video(item):
    s = item.get("statistics", {})
    sn = item.get("snippet", {})
    return {
        "video_id": item.get("id"), "title": sn.get("title", ""), "description": sn.get("description", "")[:1200],
        "published_at": sn.get("publishedAt"), "channel_title": sn.get("channelTitle", ""),
        "category_id": sn.get("categoryId"), "duration": item.get("contentDetails", {}).get("duration"),
        "views": int(s.get("viewCount", 0)), "likes": int(s.get("likeCount", 0)), "comments": int(s.get("commentCount", 0)),
    }


def build_prompt(videos):
    compact = [{"title": v["title"], "published_at": v["published_at"], "views": v["views"], "likes": v["likes"], "comments": v["comments"]} for v in videos]
    return f"""
You are the content strategist for RISE MODE, a motivational short-video brand.
Analyze ONLY the supplied YouTube performance data. Do not invent metrics.
Data:
{json.dumps(compact, ensure_ascii=False, indent=2)}

Create an actionable next-content strategy.
Rules:
- Identify repeatable themes, hooks, title patterns and publishing-time patterns supported by the data.
- Do not claim watch time or retention because those metrics are not supplied.
- Do not recommend copying existing quotes; recommend fresh variations.
- If the dataset is too small for a strong conclusion, say so and lower confidence.
- Keep recommendations practical for 10-second motivational Shorts.
- Choose TWO distinct best posting windows from the observed published_at timestamps and performance. Return exact UTC hour/minute integers. Keep at least 30 minutes between them.

Return ONLY valid JSON with exactly:
{{
  "generated_at": "",
  "overall_summary": "",
  "confidence": "low|medium|high",
  "what_is_working": [{{"pattern":"","evidence":"","action":""}}],
  "what_to_improve": [{{"pattern":"","evidence":"","action":""}}],
  "best_posting_windows": [
    {{"window":"","hour_utc":0,"minute_utc":0,"reason":"","confidence":"low|medium|high"}},
    {{"window":"","hour_utc":0,"minute_utc":0,"reason":"","confidence":"low|medium|high"}}
  ],
  "next_best_topics": [{{"priority":1,"topic":"","hook":"","format":"","reason":"","confidence":"low|medium|high"}}],
  "avoid_or_limit": [{{"item":"","reason":""}}]
}}
"""


def main():
    history = load_json(HISTORY_FILE, {"videos": []})
    existing = {x.get("video_id"): x for x in history.get("videos", [])}
    ids = discover_video_ids()
    if not ids:
        raise RuntimeError("No YouTube videos found.")
    for item in youtube_public_data(ids):
        v = normalize_video(item)
        existing[v["video_id"]] = v
    videos = sorted(existing.values(), key=lambda x: x.get("published_at") or "", reverse=True)[:MAX_VIDEOS]
    save_json(HISTORY_FILE, {"updated_at": datetime.now(timezone.utc).isoformat(), "videos": videos})

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY GitHub Secret is missing.")
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(model=GEMINI_MODEL, contents=build_prompt(videos), config=types.GenerateContentConfig(response_mime_type="application/json"))
    text = response.text.strip().removeprefix("```json").removesuffix("```").strip()
    strategy = json.loads(text)
    strategy["generated_at"] = datetime.now(timezone.utc).isoformat()
    strategy["data_points"] = len(videos)
    save_json(STRATEGY_FILE, strategy)
    print("AI CONTENT STRATEGY UPDATED")
    print("Videos analyzed:", len(videos))
    print("Strategy:", STRATEGY_FILE)


if __name__ == "__main__":
    main()
