"""Render the dashboard on the demo's made-up data to docs/img/dashboard.png for the README.

Usage: uv run python scripts/dashboard_screenshot.py
Starts Streamlit on a spare local port, opens it in the installed Chrome through Playwright and
saves the page. No real data is involved.
"""

import io
import subprocess
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

from playwright.sync_api import sync_playwright

from sales_tracker import dashboard, demo

OUT = Path(__file__).resolve().parents[1] / "docs" / "img" / "dashboard.png"
PORT = 8799


def main() -> None:
    with tempfile.TemporaryDirectory() as folder:
        work = Path(folder)
        with redirect_stdout(io.StringIO()):
            demo.run(work=work)
        config = dashboard.Config(work / "sales.db", work / "state.json", work / "katalog.yaml", True)
        args = dashboard.command(PORT) + ["--theme.base", "light"]
        server = subprocess.Popen(args, env=dashboard.environment(config))
        try:
            url = f"http://127.0.0.1:{PORT}"
            if not dashboard.wait_until_up(url):
                raise SystemExit("Streamlit se nespustil.")
            with sync_playwright() as p:
                browser = p.chromium.launch(channel="chrome", headless=True)
                tab = browser.new_page(viewport={"width": 1400, "height": 2350}, device_scale_factor=1)
                tab.goto(url)
                tab.get_by_text("Stav zdrojů").wait_for(timeout=30000)
                tab.wait_for_timeout(3000)  # chart and tables finish drawing
                OUT.parent.mkdir(parents=True, exist_ok=True)
                tab.screenshot(path=str(OUT))
                browser.close()
        finally:
            server.terminate()
            server.wait(timeout=10)
    print(f"Saved {OUT}")


if __name__ == "__main__":
    main()
