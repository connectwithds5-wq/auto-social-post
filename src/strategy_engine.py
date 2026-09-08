"""
AI Content Strategy V3
Collects public YouTube performance plus owner-only YouTube Analytics metrics
using the existing YOUTUBE_OAUTH_JSON credential, then asks Gemini for strategy.
"""

import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
from google import genai
from google.genai import types
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

ROOT = Path(__file__).resolve().parents[1]
HISTORY_FILE = ROOT / "strategy_history.json"
STRATEGY_FILE = ROOT / "strategy.json"
CHANNEL_ID = os.environ.get("YOUTUBE_CHANNEL_ID", "").strip()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash").strip()
MAX_VIDEOS = 50
ANALYTICS_VIDEO_LIMIT = 20

YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


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
    api_key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("YOUTUBE_API_KEY GitHub Secret is missing.")
    r = requests.get(
        "https://www.googleapis.com/youtube/v3/videos",
        params={"part": "snippet,statistics,contentDetails", "id": ",".join(video_ids[:50]), "key": api_key},
        timeout=30,
    )
    if not r.ok:
        raise RuntimeError(f"YouTube API {r.status_code}: {r.text[:500]}")
    return r.json().get("items", [])


def discover_video_ids():
    api_key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("YOUTUBE_API_KEY GitHub Secret is missing.")
    if not CHANNEL_ID:
        raise RuntimeError("YOUTUBE_CHANNEL_ID is missing.")
    r = requests.get(
        "https://www.googleapis.com/youtube/v3/channels",
        params={"part": "contentDetails", "id": CHANNEL_ID, "key": api_key},
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
        params={"part": "contentDetails", "playlistId": uploads, "maxResults": MAX_VIDEOS, "key": api_key},
        timeout=30,
    )
    if not r.ok:
        raise RuntimeError(f"YouTube playlist API {r.status_code}: {r.text[:500]}")
    return [x["contentDetails"]["videoId"] for x in r.json().get("items", []) if x.get("contentDetails", {}).get("videoId")]


def normalize_video(item):
    s = item.get("statistics", {})
    sn = item.get("snippet", {})
    return {
        "video_id": item.get("id"), "title": sn.get("title", ""),
        "description": sn.get("description", "")[:1200], "published_at": sn.get("publishedAt"),
        "channel_title": sn.get("channelTitle", ""), "category_id": sn.get("categoryId"),
        "duration": item.get("contentDetails", {}).get("duration"),
        "views": int(s.get("viewCount", 0)), "likes": int(s.get("likeCount", 0)),
        "comments": int(s.get("commentCount", 0)),
    }


def load_oauth_credentials():
    raw = os.environ.get("YOUTUBE_OAUTH_JSON", "").strip()
    if not raw:
        raise RuntimeError("YOUTUBE_OAUTH_JSON GitHub Secret is missing.")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("YOUTUBE_OAUTH_JSON is not valid JSON.") from exc
    missing = [k for k in ("client_id", "client_secret", "refresh_token") if not data.get(k)]
    if missing:
        raise RuntimeError("YOUTUBE_OAUTH_JSON is missing: " + ", ".join(missing))
    credentials = Credentials.from_authorized_user_info(data, YOUTUBE_SCOPES)
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
    if not credentials.valid:
        raise RuntimeError("YouTube OAuth credentials are invalid.")
    return credentials


def youtube_owner_analytics(public_videos):
    credentials = load_oauth_credentials()
    analytics_api = build("youtubeAnalytics", "v2", credentials=credentials, cache_discovery=False)
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=365)

    params = {
        "ids": "channel==MINE",
        "startDate": start.isoformat(),
        "endDate": today.isoformat(),
        "dimensions": "video",
        "metrics": "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,likes,comments,shares,subscribersGained,subscribersLost",
        "sort": "-views",
        "maxResults": 200,
    }
    report = analytics_api.reports().query(**params).execute()
    headers = [h["name"] for h in report.get("columnHeaders", [])]
    analytics = {}
    for row in report.get("rows", []):
        item = dict(zip(headers, row))
        video_id = item.pop("video", None)
        if video_id:
            analytics[video_id] = item

    retention = {}
    candidates = sorted(public_videos, key=lambda x: x.get("published_at") or "", reverse=True)[:ANALYTICS_VIDEO_LIMIT]
    for video in candidates:
        video_id = video.get("video_id")
        published = (video.get("published_at") or "")[:10]
        if not video_id or not published:
            continue
        try:
            report = analytics_api.reports().query(
                ids="channel==MINE",
                startDate=published,
                endDate=today.isoformat(),
                dimensions="elapsedVideoTimeRatio",
                metrics="audienceWatchRatio,relativeRetentionPerformance",
                filters=f"video=={video_id}",
                sort="elapsedVideoTimeRatio",
                maxResults=200,
            ).execute()
            rh = [h["name"] for h in report.get("columnHeaders", [])]
            points = [dict(zip(rh, row)) for row in report.get("rows", [])]
            if points:
                retention[video_id] = points
        except Exception as exc:
            print(f"Retention unavailable for {video_id}: {exc}")

    return analytics, retention, "youtube_analytics_api"


def summarize_retention(points):
    if not points:
        return None
    sampled = []
    for point in points:
        try:
            ratio = float(point.get("elapsedVideoTimeRatio", 0))
            watch = float(point.get("audienceWatchRatio", 0))
            relative = float(point.get("relativeRetentionPerformance", 0))
        except (TypeError, ValueError):
            continue
        if ratio <= 0.10 or abs(ratio - 0.25) < 0.02 or abs(ratio - 0.50) < 0.02 or abs(ratio - 0.75) < 0.02 or ratio >= 0.90:
            sampled.append({
                "video_progress": round(ratio, 3),
                "audience_watch_ratio": round(watch, 4),
                "relative_retention": round(relative, 4),
            })
    return sampled[:15]


def build_prompt(videos, analytics, retention, source):
    compact = []
    for video in videos:
        row = {
            "title": video["title"], "published_at": video["published_at"],
            "views": video["views"], "likes": video["likes"], "comments": video["comments"],
        }
        if source == "youtube_analytics_api":
            if video["video_id"] in analytics:
                row["youtube_studio"] = analytics[video["video_id"]]
            rp = summarize_retention(retention.get(video["video_id"], []))
            if rp:
                row["retention_curve"] = rp
        compact.append(row)

    return f"""
You are the content strategist for RISE MODE, a motivational short-video brand.
Analyze ONLY the supplied YouTube performance data. Never invent metrics.
Analytics source: {source}
If owner analytics are present, use average view duration, average percentage watched,
estimated watch time, likes/comments/shares, subscriber conversion and retention curves.
Use retention curves to identify early drop-offs, strong hold zones and payoff timing.
If a metric is absent, do not infer it. Do not claim Studio-only metrics when source is public_only.

For 10-second Shorts, turn evidence into concrete guidance on hook length, pacing,
payoff timing, visual density, CTA timing, topic and publishing time.
Prefer repeatable patterns over one-off outliers.
Do not recommend copying existing quotes; recommend fresh variations.
Choose TWO distinct best posting windows from observed published_at timestamps and performance.
Return exact UTC hour/minute integers, at least 30 minutes apart.

Return ONLY valid JSON with exactly:
{{
  "generated_at":"",
  "overall_summary":"",
  "confidence":"low|medium|high",
  "analytics_source":"public_only|youtube_analytics_api",
  "what_is_working":[{{"pattern":"","evidence":"","action":""}}],
  "what_to_improve":[{{"pattern":"","evidence":"","action":""}}],
  "retention_insights":[{{"video_pattern":"","drop_or_strength":"","evidence":"","action":""}}],
  "best_posting_windows":[
    {{"window":"","hour_utc":0,"minute_utc":0,"reason":"","confidence":"low|medium|high"}},
    {{"window":"","hour_utc":0,"minute_utc":0,"reason":"","confidence":"low|medium|high"}}
  ],
  "next_best_topics":[{{"priority":1,"topic":"","hook":"","format":"","reason":"","confidence":"low|medium|high"}}],
  "avoid_or_limit":[{{"item":"","reason":""}}]
}}

YOUTUBE DATA:
{json.dumps(compact, ensure_ascii=False, indent=2)}
"""


def main():
    history = load_json(HISTORY_FILE, {"videos": []})
    existing = {x.get("video_id"): x for x in history.get("videos", [])}
    ids = discover_video_ids()
    if not ids:
        raise RuntimeError("No YouTube videos found.")
    for item in youtube_public_data(ids):
        video = normalize_video(item)
        existing[video["video_id"]] = video
    videos = sorted(existing.values(), key=lambda x: x.get("published_at") or "", reverse=True)[:MAX_VIDEOS]

    analytics, retention, source = youtube_owner_analytics(videos)
    for video in videos:
        if video["video_id"] in analytics:
            video["owner_analytics"] = analytics[video["video_id"]]
        rp = summarize_retention(retention.get(video["video_id"], []))
        if rp:
            video["retention_curve"] = rp

    save_json(HISTORY_FILE, {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "analytics_source": source,
        "videos": videos,
    })

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY GitHub Secret is missing.")
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=build_prompt(videos, analytics, retention, source),
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    text = response.text.strip().removeprefix("```json").removesuffix("```").strip()
    strategy = json.loads(text)
    strategy["generated_at"] = datetime.now(timezone.utc).isoformat()
    strategy["data_points"] = len(videos)
    strategy["analytics_source"] = source
    strategy["owner_analytics_videos"] = len(analytics)
    strategy["retention_videos"] = len(retention)
    save_json(STRATEGY_FILE, strategy)

    print("AI CONTENT STRATEGY UPDATED")
    print("Videos analyzed:", len(videos))
    print("Analytics source:", source)
    print("Owner analytics videos:", len(analytics))
    print("Retention reports:", len(retention))
    print("Strategy:", STRATEGY_FILE)


if __name__ == "__main__":
    main()
