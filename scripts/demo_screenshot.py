"""Render the demo's morning report (made-up data) to docs/img/morning-report.png for the README.

Usage: uv run python scripts/demo_screenshot.py
Uses the installed Chrome through Playwright, like the Cosmos agent. No real data is involved.
"""

import html
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

from sales_tracker import demo

OUT = Path(__file__).resolve().parents[1] / "docs" / "img" / "morning-report.png"


def main() -> None:
    reports = []
    demo.run(send=reports.append)
    report = reports[0]
    page = f"""<!doctype html><meta charset="utf-8">
<body style="margin:0;background:#f3f4f6;font-family:Segoe UI,Arial,sans-serif">
<div style="max-width:760px;margin:24px auto;background:#fff;border:1px solid #e5e7eb;border-radius:8px">
<div style="padding:16px 24px;border-bottom:1px solid #e5e7eb;color:#374151;font-size:13px">
<div><b>From:</b> Sales tracker &lt;onboarding@resend.dev&gt;</div>
<div style="font-size:17px;margin-top:6px;color:#111827"><b>{html.escape(report.subject)}</b></div></div>
<div style="padding:4px 24px 16px">{report.html()}</div></div></body>"""
    with tempfile.TemporaryDirectory() as folder:
        source = Path(folder) / "report.html"
        source.write_text(page, encoding="utf-8")
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            tab = browser.new_page(viewport={"width": 820, "height": 600}, device_scale_factor=2)
            tab.goto(source.as_uri())
            OUT.parent.mkdir(parents=True, exist_ok=True)
            tab.screenshot(path=str(OUT), full_page=True)
            browser.close()
    print(f"Saved {OUT}")


if __name__ == "__main__":
    main()
