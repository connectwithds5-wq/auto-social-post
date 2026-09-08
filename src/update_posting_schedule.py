"""Apply AI-selected UTC posting windows to the Auto Social Post workflow."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STRATEGY = ROOT / "strategy.json"
WORKFLOW = ROOT / ".github" / "workflows" / "generate.yml"


def main():
    strategy = json.loads(STRATEGY.read_text(encoding="utf-8"))
    windows = strategy.get("best_posting_windows") or []
    valid = []
    for w in windows:
        try:
            hour = int(w["hour_utc"])
            minute = int(w["minute_utc"])
        except (KeyError, TypeError, ValueError):
            continue
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            valid.append((hour, minute))
    unique = list(dict.fromkeys(valid))[:2]
    if len(unique) < 2:
        print("Not enough valid AI posting windows; keeping existing schedule.")
        return
    unique.sort()
    source = WORKFLOW.read_text(encoding="utf-8")
    block = re.compile(r'(  schedule:\n)(    - cron: "[^\n]+"\n)(    - cron: "[^\n]+"\n)')
    replacement = "  schedule:\n" + ''.join(f'    - cron: "{m} {h} * * *"\n' for h, m in unique)
    updated, count = block.subn(replacement, source, count=1)
    if count != 1:
        raise RuntimeError("Could not locate the two-slot schedule block")
    if updated == source:
        print("Posting schedule already matches AI strategy:", unique)
        return
    WORKFLOW.write_text(updated, encoding="utf-8")
    print("AI posting schedule updated to UTC windows:", unique)


if __name__ == "__main__":
    main()
