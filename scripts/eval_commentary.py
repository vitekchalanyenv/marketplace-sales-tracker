"""Eval of the weekly commentary against the real model, on the demo's made-up data.

Asks Claude N times for the commentary on the same week and records how often it passed the check
on the first attempt, after the retry, or not at all, and which rules rejected it. Costs real
money (a few cents per run), so it is run by hand, never in tests or CI.

Usage: uv run python scripts/eval_commentary.py [runs]   (needs ANTHROPIC_API_KEY in .env)
Writes docs/eval/commentary-real-model.json (made-up data only, safe to commit).
"""

import io
import json
import os
import sys
import tempfile
from collections import Counter
from contextlib import redirect_stdout
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

from sales_tracker import daily, db, demo, weekly

OUT = Path(__file__).resolve().parents[1] / "docs" / "eval" / "commentary-real-model.json"
CATEGORIES = [
    ("číslo napsané přímo", "number written out"),
    ("číslovka slovem", "number / quantity word"),
    ("vlastní směr změny", "own direction"),
    ("vlastní pořadí", "own ranking"),
    ("vlastní příčina", "own cause"),
    ("název produktu napsaný přímo", "product name written out"),
    ("neznámá značka", "unknown placeholder"),
    ("patří k", "value next to the wrong name"),
    ("stojí ve větě bez názvu", "value without a name"),
]


def category(problem: str) -> str:
    for marker, name in CATEGORIES:
        if marker in problem:
            return name
    return "other"


def demo_facts(work: Path) -> dict:
    with redirect_stdout(io.StringIO()):
        demo.run(work=work)
    conn = db.connect(work / "sales.db")
    try:
        day = demo.NOW.astimezone(daily.LOCAL_TZ).date()
        return weekly.week_facts(
            conn, day, daily.CzkConverter(demo.DemoRates()), demo._product_names(work / "katalog.yaml")
        )
    finally:
        conn.close()


def main(runs: int) -> None:
    load_dotenv(Path.cwd() / ".env")
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        sys.exit("Chybí ANTHROPIC_API_KEY v .env.")
    with tempfile.TemporaryDirectory() as folder:
        facts = demo_facts(Path(folder))
    claude = weekly.ClaudeWriter(key)

    results = []
    for number in range(1, runs + 1):
        texts: list[str] = []

        def writer(available, rejected, texts=texts):
            texts.append(claude(available, rejected))
            return texts[-1]

        comment = weekly.commentary(facts, writer)
        if comment.text is not None:
            outcome = "first" if len(texts) == 1 else "retry"
        elif comment.rejected:
            outcome = "gave_up"
        else:
            outcome = "error"
        results.append({
            "outcome": outcome,
            "attempts": [{"text": t, "problems": list(p)} for t, p in comment.rejected]
            + ([{"text": texts[-1], "problems": []}] if comment.text is not None else []),
            "final": comment.text,
            "note": comment.note,
        })
        print(f"{number:2d}/{runs}: {outcome}", flush=True)

    outcomes = Counter(r["outcome"] for r in results)
    rules = Counter(
        category(problem) for r in results for a in r["attempts"] for problem in a["problems"]
    )
    summary = {
        "date": datetime.now(UTC).strftime("%Y-%m-%d"),
        "model": weekly.MODEL,
        "data": "demo (made-up), week " + facts["obdobi"],
        "runs": runs,
        "first_attempt": outcomes["first"],
        "after_retry": outcomes["retry"],
        "gave_up": outcomes["gave_up"],
        "api_error": outcomes["error"],
        "rejections_by_rule": dict(rules.most_common()),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Saved {OUT}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 20)
