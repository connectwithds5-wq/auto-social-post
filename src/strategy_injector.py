"""
Apply the latest AI strategy to the existing video generator at runtime.
The repository generator is not permanently rewritten; this only injects the
current strategy into the prompt inside the GitHub Actions runner.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STRATEGY_FILE = ROOT / "strategy.json"
GENERATOR_FILE = ROOT / "src" / "generate_video.py"


def main():
    if not STRATEGY_FILE.exists():
        print("No strategy.json found. Using normal generator prompt.")
        return

    try:
        strategy = json.loads(STRATEGY_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Could not read strategy.json: {exc}")
        return

    topics = strategy.get("next_best_topics") or []
    if not topics:
        print("No next_best_topics found. Using normal generator prompt.")
        return

    # Earlier daily run = priority 1, later daily run = priority 2.
    # This lets both recommended angles get tested automatically.
    hour = datetime.now(timezone.utc).hour
    selected = topics[0] if hour < 9 else (topics[1] if len(topics) > 1 else topics[0])

    topic = str(selected.get("topic", "")).strip()
    hook = str(selected.get("hook", "")).strip()
    fmt = str(selected.get("format", "")).strip()
    reason = str(selected.get("reason", "")).strip()
    confidence = str(
        selected.get("confidence", strategy.get("confidence", "low"))
    ).strip()

    if not topic:
        print("Selected strategy topic is empty. Using normal generator prompt.")
        return

    context = f"""
STRATEGY ENGINE DIRECTIVE — FOLLOW THIS FOR THIS VIDEO

The latest RISE MODE performance analysis selected this topic because it is a
recommended next-best content direction. Create a FRESH original quote and
metadata around this strategy. Do not copy any existing quote.

Recommended topic: {topic}
Recommended hook direction: {hook}
Recommended format: {fmt}
Why this was selected: {reason}
Strategy confidence: {confidence}

Execution rules:
- Make the quote strongly aligned with the recommended topic and hook direction.
- Keep the quote original; do not reuse wording from existing videos.
- Make the title specific, emotional and action-oriented rather than generic.
- Preserve the existing RISE MODE brand, English-only requirement and all safety rules.
- Follow the recommended format as closely as possible within the existing 10-second video pipeline.
""".strip()

    source = GENERATOR_FILE.read_text(encoding="utf-8")
    marker = 'prompt = """'
    start = source.find(marker)
    if start < 0:
        raise RuntimeError("Could not find generator prompt block.")

    content_start = start + len(marker)
    end = source.find('"""', content_start)
    if end < 0:
        raise RuntimeError("Could not find end of generator prompt block.")

    original_prompt = source[content_start:end]

    if "STRATEGY ENGINE DIRECTIVE — FOLLOW THIS FOR THIS VIDEO" in original_prompt:
        print("Strategy directive already applied.")
        return

    new_prompt = "\n\n" + context + "\n\n" + original_prompt.lstrip("\n")
    updated = source[:content_start] + new_prompt + source[end:]
    GENERATOR_FILE.write_text(updated, encoding="utf-8")

    print("========================================")
    print("      AI STRATEGY APPLIED TO VIDEO")
    print("========================================")
    print("Topic:", topic)
    print("Hook:", hook)
    print("Format:", fmt)
    print("Confidence:", confidence)
    print("UTC hour:", hour)
    print("========================================")


if __name__ == "__main__":
    main()
