"""Spike (M4a, option A): can Playwright read Cosmos sales through the page's own API call?

Not production code. Questions it answers (docs/spec/M4-prohlizec-moznosti.md):
  1. Does a dedicated Chrome profile keep the Cosmos login between runs?
  2. Can we capture the JSON the page itself loads from api.publisher.leartesstudios.com/sales?
  3. Does it work headless (Cloudflare)?

The script never reads, prints or stores the login token or password. Vítek logs in himself
in the opened window (reCAPTCHA). Captured JSON goes to data/private/ only; the console shows
only the structure (keys and types), never values.

Usage:
  uv run python spikes/cosmos_playwright.py login      # opens Chrome, wait for Vítek to log in
  uv run python spikes/cosmos_playwright.py fetch      # headed run, capture JSON
  uv run python spikes/cosmos_playwright.py fetch --headless
"""

import argparse
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import Response, sync_playwright

PROFILE_DIR = Path("data/private/browser/cosmos")
OUT_DIR = Path("data/private/cosmos")
SALES_PAGE = "https://publisher.leartesstudios.com/sales"
API_PREFIX = "https://api.publisher.leartesstudios.com/sales"
LOGIN_TIMEOUT_S = 600


def shape(value, depth=0):
    """Structure without values: dict keys -> types, lists -> length + first item."""
    if isinstance(value, dict) and depth < 6:
        return {k: shape(v, depth + 1) for k, v in value.items()}
    if isinstance(value, list):
        return {"list": len(value), "item": shape(value[0], depth + 1) if value else None}
    return type(value).__name__


def open_context(p, headless: bool):
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    return p.chromium.launch_persistent_context(
        str(PROFILE_DIR), channel="chrome", headless=headless, viewport={"width": 1400, "height": 900}
    )


def capture_sales(page, timeout_s: float) -> tuple[int, dict | None]:
    """Load the sales page and return (status, json) of the page's own API response."""
    captured: list[Response] = []
    page.on("response", lambda r: captured.append(r) if r.url.startswith(API_PREFIX) else None)
    page.goto(SALES_PAGE, wait_until="domcontentloaded")
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for response in captured:
            if response.status == 200:
                return 200, response.json()
        page.wait_for_timeout(500)
    status = captured[-1].status if captured else 0
    return status, None


def cmd_login() -> int:
    with sync_playwright() as p:
        context = open_context(p, headless=False)
        page = context.pages[0] if context.pages else context.new_page()
        print(f"Okno Chromu je otevřené. Přihlas se do Cosmosu (máš {LOGIN_TIMEOUT_S // 60} minut).")
        print("Až uvidíš tabulku Sales, skript to pozná sám a okno zavře.")
        status, data = capture_sales(page, LOGIN_TIMEOUT_S)
        if data is None:
            # after logging in, the app may land on the dashboard: try the sales page once more
            status, data = capture_sales(page, 30)
        context.close()
    print("Přihlášení OK, API odpovědělo 200." if data is not None else f"Nepodařilo se (poslední status {status}).")
    return 0 if data is not None else 1


def cmd_fetch(headless: bool) -> int:
    started = time.monotonic()
    with sync_playwright() as p:
        context = open_context(p, headless=headless)
        page = context.pages[0] if context.pages else context.new_page()
        status, data = capture_sales(page, 45)
        final_url = page.url
        context.close()
    elapsed = time.monotonic() - started
    mode = "headless" if headless else "s oknem"
    if data is None:
        print(f"[{mode}] Data nezachycena: status {status}, stránka skončila na {final_url.split('?')[0]}")
        return 1
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"api_sample_{'headless' if headless else 'headed'}.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[{mode}] OK za {elapsed:.1f} s, uloženo do {out}")
    print(json.dumps(shape(data), indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["login", "fetch"])
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()
    return cmd_login() if args.command == "login" else cmd_fetch(args.headless)


if __name__ == "__main__":
    sys.exit(main())
