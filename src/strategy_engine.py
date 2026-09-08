"""
AI Content Strategy V3
Collects public YouTube performance plus owner-only YouTube Analytics metrics
when OAuth credentials are configured, then asks Gemini for next-content strategy.
"""

import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
from google import genai
from google.genai import types

ROOT = Path(__file__).resolve().parents[1]
HISTORY_FILE = ROOT / "strategy_history.json"
STRATEGY_FILE = ROOT / "strategy.json"
CHANNEL_ID = os.environ.get("YOUTUBE_CHANNEL_ID", "").strip()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash").strip()
MAX_VIDEOS = 50
ANALYTICS_VIDEO_LIMIT = 20


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
    ids = ",".join(video_ids[:50])
    r = requests.get(
        "https://www.googleapis.com/youtube/v3/videos",
        params={"part": "snippet,statistics,contentDetails", "id": ids, "key": api_key},
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
        raise RuntimeError("YOUTUBE_CHANNEL_ID GitHub Variable is missing.")
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


def oauth_access_token():
    client_id = os.environ.get("YOUTUBE_CLIENT_ID", "").strip()
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET", "").strip()
    refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN", "").strip()
    if not all([client_id, client_secret, refresh_token]):
        return None
    r = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    if not r.ok:
        raise RuntimeError(f"YouTube OAuth token refresh failed: {r.status_code}: {r.text[:500]}")
    token = r.json().get("access_token")
    if not token:
        raise RuntimeError("YouTube OAuth token response did not contain an access token.")
    return token


def analytics_request(access_token, params):
    r = requests.get(
        "https://youtubeanalytics.googleapis.com/v2/reports",
        params=params,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=45,
    )
    if not r.ok:
        raise RuntimeError(f"YouTube Analytics API {r.status_code}: {r.text[:800]}")
    return r.json()


def youtube_owner_analytics(video_ids, public_videos):
    """Return owner-only Analytics API data when OAuth secrets are configured."""
    access_token = oauth_access_token()
    if not access_token:
        return {}, {}, "public_only"

    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=365)
    base_params = {
        "ids": "channel==MINE",
        "startDate": start.isoformat(),
        "endDate": today.isoformat(),
        "dimensions": "video",
        "metrics": "views,engagedViews,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,likes,comments,shares,subscribersGained,subscribersLost",
        "maxResults": 200,
    }
    data = analytics_request(access_token, base_params)
    headers = [h["name"] for h in data.get("columnHeaders", [])]
    analytics = {}
    for row in data.get("rows", []):
        item = dict(zip(headers, row))
        vid = item.pop("video", None)
        if vid:
            analytics[vid] = item

    retention = {}
    candidates = sorted(
        public_videos,
        key=lambda x: x.get("published_at") or "",
        reverse=True,
    )[:ANALYTICS_VIDEO_LIMIT]
    for video in candidates:
        vid = video.get("video_id")
        published = (video.get("published_at") or "")[:10]
        if not vid or not published:
            continue
        try:
            rp = analytics_request(
                access_token,
                {
                    "ids": "channel==MINE",
                    "startDate": published,
                    "endDate": today.isoformat(),
                    "dimensions": "elapsedVideoTimeRatio",
                    "metrics": "audienceWatchRatio,relativeRetentionPerformance,startedWatching,stoppedWatching,totalSegmentImpressions",
                    "filters": f"video=={vid}",
                    "maxResults": 200,
                },
            )
            rh = [h["name"] for h in rp.get("columnHeaders", [])]
            points = []
            for row in rp.get("rows", []):
                item = dict(zip(rh, row))
                points.append(item)
            retention[vid] = points
        except Exception as exc:
            print(f"Retention unavailable for {vid}: {exc}")

    return analytics, retention, "youtube_analytics_api"


def summarize_retention(points):
    if not points:
        return None
    wanted = []
    for point in points:
        try:
            ratio = float(point.get("elapsedVideoTimeRatio", 0))
        except (TypeError, ValueError):
            continue
        if ratio <= 0.10 or abs(ratio - 0.25) < 0.02 or abs(ratio - 0.50) < 0.02 or abs(ratio - 0.75) < 0.02 or ratio >= 0.90:
            wanted.append({
                "video_progress": round(ratio, 3),
                "audience_watch_ratio": round(float(point.get("audienceWatchRatio", 0)), 4),
                "relative_retention": round(float(point.get("relativeRetentionPerformance", 0)), 4),
                "started_watching": point.get("startedWatching"),
                "stopped_watching": point.get("stoppedWatching"),
            })
    return wanted[:15]


def build_prompt(videos, analytics, retention, source):
    compact = []
    for v in videos:
        row = {
            "title": v["title"],
            "published_at": v["published_at"],
            "views": v["views"],
            "likes": v["likes"],
            "comments": v["comments"],
        }
        if source == "youtube_analytics_api":
            a = analytics.get(v["video_id"], {})
            if a:
                row["owner_analytics"] = a
            rp = summarize_retention(retention.get(v["video_id"], []))
            if rp:
                row["retention_curve"] = rp
        compact.append(row)

    analytics_rules = (
        "Owner-only YouTube Analytics metrics are included. Use them to identify retention drops, engaged-view quality, watch time, average percentage watched, and subscriber conversion. "
        "Retention points are sampled from the official audience-retention report; do not claim a metric that is absent from the supplied data."
        if source == "youtube_analytics_api"
        else
        "Owner-only YouTube Analytics is not configured. Analyze only the supplied public metrics and do not claim watch time or retention."
    )

    return f"""
You are the content strategist for RISE MODE, a motivational short-video brand.
Analyze ONLY the supplied YouTube performance data. Never invent metrics.
Analytics source: {source}
{analytics_rules}
Data:
{json.dumps(compact, ensure_ascii=False, indent=2)}

Create an actionable next-content strategy.
Rules:
- Identify repeatable themes, hooks, title patterns and publishing-time patterns supported by the data.
- If owner analytics are available, explicitly connect recommendations to retention, average view percentage, engaged views, watch time, shares and subscriber conversion where present.
- For retention, identify likely early-drop zones and strong retention zones from the supplied elapsed-video-time samples.
- Do not recommend copying existing quotes; recommend fresh variations.
- If the dataset is too small for a strong conclusion, say so and lower confidence.
- Keep recommendations practical for 10-second motivational Shorts.
- Choose TWO distinct best posting windows from the observed published_at timestamps and performance. Return exact UTC hour/minute integers. Keep at least 30 minutes between them.

Return ONLY valid JSON with exactly:
{{
  "generated_at": "",
  "overall_summary": "",
  "confidence": "low|medium|high",
  "analytics_source": "public_only|youtube_analytics_api",
  "what_is_working": [{{"pattern":"","evidence":"","action":""}}],
  "what_to_improve": [{{"pattern":"","evidence":"","action":""}}],
  "retention_insights": [{{"video_pattern":"","drop_or_strength":"","evidence":"","action":""}}],
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
    public_items = youtube_public_data(ids)
    for item in public_items:
        v = normalize_video(item)
        existing[v["video_id"]] = v
    videos = sorted(existing.values(), key=lambda x: x.get("published_at") or "", reverse=True)[:MAX_VIDEOS]

    analytics, retention, source = youtube_owner_analytics(ids, videos)
    for v in videos:
        if v["video_id"] in analytics:
            v["owner_analytics"] = analytics[v["video_id"]]
        rp = summarize_retention(retention.get(v["video_id"], []))
        if rp:
            v["retention_curve"] = rp

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
