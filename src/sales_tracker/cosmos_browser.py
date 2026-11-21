"""Cosmos browser agent: a dedicated Chrome profile reads the JSON the sales page loads itself.

Thin on purpose: page logic (paging, stop rule, validation) lives in cosmos.py and is tested
without a browser. Here we only open Chrome, load /sales?page=N and hand back the captured
API response. The login token never passes through this code: the browser profile holds the
session, Vítek logs in himself (reCAPTCHA). Verified by the spike in spikes/cosmos_playwright.py.
"""

import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Self

from sales_tracker.cosmos import FetchError, SessionExpired

PROFILE_DIR = Path("data/private/browser/cosmos")
SCREENSHOT_DIR = Path("data/private/cosmos")
SALES_URL = "https://publisher.leartesstudios.com/sales"
API_PREFIX = "https://api.publisher.leartesstudios.com/sales"
PAGE_TIMEOUT_S = 45
LOGIN_TIMEOUT_S = 600


class CosmosBrowser:
    """Context manager: `with CosmosBrowser() as browser: browser.load_page(1)`."""

    def __init__(self, *, headless: bool = True, profile_dir: Path = PROFILE_DIR):
        self.headless = headless
        self.profile_dir = profile_dir

    def __enter__(self) -> Self:
        from playwright.sync_api import sync_playwright  # heavy import, only when the agent runs

        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = sync_playwright().start()
        self._context = self._playwright.chromium.launch_persistent_context(
            str(self.profile_dir), channel="chrome", headless=self.headless,
            viewport={"width": 1400, "height": 900},
        )
        self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
        return self

    def __exit__(self, *exc) -> None:
        self._context.close()
        self._playwright.stop()

    def _capture(self, url: str, page_number: int, timeout_s: float):
        responses = []

        def on_response(response):
            if response.url.startswith(API_PREFIX) and f"page={page_number}" in response.url:
                responses.append(response)

        self._page.on("response", on_response)
        try:
            self._page.goto(url, wait_until="domcontentloaded")
            deadline = time.monotonic() + timeout_s
            while time.monotonic() < deadline:
                for response in responses:
                    if response.status == 200:
                        return response
                if any(r.status in (401, 403) for r in responses):
                    break
                self._page.wait_for_timeout(500)
            return None
        finally:
            self._page.remove_listener("response", on_response)

    def load_page(self, number: int) -> dict:
        response = self._capture(f"{SALES_URL}?page={number}", number, PAGE_TIMEOUT_S)
        if response is None:
            if "/sales" not in self._page.url:
                raise SessionExpired(f"stránka skončila na {self._page.url.split('?')[0]}")
            self._screenshot("no-response")
            raise SessionExpired("Cosmos nevrátil prodeje (nejspíš vypršelo přihlášení)")
        try:
            return response.json()
        except ValueError:
            self._screenshot("not-json")
            raise FetchError("odpověď API Cosmosu není JSON") from None

    def wait_for_login(self) -> bool:
        """Headed window: wait until Vítek has logged in and the sales page loads its data."""
        return self._capture(SALES_URL, 1, LOGIN_TIMEOUT_S) is not None or (
            self._capture(SALES_URL, 1, 30) is not None
        )

    def _screenshot(self, reason: str) -> None:
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        self._page.screenshot(path=str(SCREENSHOT_DIR / f"error_{stamp}_{reason}.png"))
