"""Gumroad: fetching sales from API v2 and mapping them to the common model.

Field meanings are documented in docs/ZDROJE.md (taken from Gumroad's docs and source code).
"""

import ssl
import time
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any

import httpx

from sales_tracker.models import Sale, Status

MARKETPLACE = "gumroad"
BASE_URL = "https://api.gumroad.com/v2"
ATTEMPTS = 3
RETRY_PAUSE_SECONDS = 5.0
PAGE_PAUSE_SECONDS = 1.0
TIMEOUT_SECONDS = 30.0


class GumroadError(Exception):
    """Gumroad request failed. The message never contains the token."""


class GumroadAuthError(GumroadError):
    """401/403: invalid token or missing view_sales scope."""


class SkipRecord(Exception):
    """A sale record that cannot be mapped. Carries only the ID and a reason, no personal data."""

    def __init__(self, external_id: str | None, reason: str):
        super().__init__(f"{external_id}: {reason}")
        self.external_id = external_id
        self.reason = reason


class GumroadClient:
    def __init__(
        self,
        token: str,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._http = httpx.Client(
            base_url=BASE_URL,
            headers={"Authorization": f"Bearer {token}"},
            timeout=TIMEOUT_SECONDS,
            transport=transport,
            # Trust the operating system's certificate store instead of certifi's bundle:
            # on Vítek's machine HTTPS goes through a locally trusted certificate (antivirus/proxy)
            # that only the Windows store knows. Verification stays on.
            verify=ssl.create_default_context(),
        )
        self._sleep = sleep

    def fetch_sales(self, after: date | None = None) -> list[dict[str, Any]]:
        """All sales (newest first), following next_page_key until the last page."""
        params: dict[str, str] = {}
        if after is not None:
            params["after"] = after.isoformat()

        records: list[dict[str, Any]] = []
        while True:
            body = self._get("/sales", params)
            sales = body.get("sales")
            if not isinstance(sales, list):
                raise GumroadError("Neočekávaná odpověď Gumroadu: chybí seznam 'sales'.")
            records.extend(sales)

            next_key = body.get("next_page_key")
            if not next_key:
                return records
            params = {**params, "page_key": next_key}
            self._sleep(PAGE_PAUSE_SECONDS)

    def _get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        problem = ""
        for attempt in range(1, ATTEMPTS + 1):
            try:
                response = self._http.get(path, params=params)
            except httpx.HTTPError as exc:
                # httpx messages contain host and reason, never request headers (the token)
                problem = f"chyba sítě ({type(exc).__name__}: {str(exc)[:200]})"
            else:
                if response.status_code in (401, 403):
                    raise GumroadAuthError(f"HTTP {response.status_code}")
                if response.status_code < 500:
                    return self._parse(response)
                problem = f"HTTP {response.status_code}"
            if attempt < ATTEMPTS:
                self._sleep(RETRY_PAUSE_SECONDS * attempt)
        raise GumroadError(f"Gumroad neodpověděl ani po {ATTEMPTS} pokusech: {problem}.")

    @staticmethod
    def _parse(response: httpx.Response) -> dict[str, Any]:
        try:
            body = response.json()
        except ValueError:
            raise GumroadError(f"Odpověď Gumroadu není JSON (HTTP {response.status_code}).") from None
        if not isinstance(body, dict):
            raise GumroadError("Neočekávaná odpověď Gumroadu.")
        if response.status_code >= 400 or body.get("success") is not True:
            message = body.get("message") or "bez zprávy"
            raise GumroadError(f"Gumroad vrátil chybu (HTTP {response.status_code}): {message}")
        return body


def _cents(record: dict[str, Any], key: str, external_id: str) -> int:
    value = record[key]
    # bool is a subclass of int; floats are refused on purpose (money is never float)
    if type(value) is not int or value < 0:
        raise SkipRecord(external_id, f"pole '{key}' není nezáporné celé číslo v centech")
    return value


def _status(record: dict[str, Any]) -> Status:
    # Gumroad omits fields whose value is null, so a missing flag means false.
    if record.get("chargedback"):
        return Status.CHARGEBACK
    if record.get("refunded"):
        return Status.REFUNDED
    if record.get("partially_refunded"):
        return Status.PARTIALLY_REFUNDED
    return Status.SOLD


def parse_sale(record: dict[str, Any]) -> Sale:
    """Map one /v2/sales record to the common model. Raises SkipRecord if it cannot be used."""
    external_id = record.get("id")
    if not isinstance(external_id, str) or not external_id:
        raise SkipRecord(None, "chybí pole 'id'")

    created_at = record.get("created_at")
    try:
        sold_at = datetime.fromisoformat(created_at)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise SkipRecord(external_id, "pole 'created_at' chybí nebo není čas ISO 8601") from None
    if sold_at.tzinfo is None:
        raise SkipRecord(external_id, "pole 'created_at' nemá časovou zónu")

    if "price" not in record:
        raise SkipRecord(external_id, "chybí pole 'price'")
    gross = _cents(record, "price", external_id)
    # gumroad_fee already includes the processing fee for sales through Gumroad's merchant account
    net = gross - _cents(record, "gumroad_fee", external_id) if "gumroad_fee" in record else None

    return Sale(
        marketplace=MARKETPLACE,
        external_id=external_id,
        product_title=record.get("product_name"),
        product_ref=record.get("product_id"),
        sold_at=sold_at.astimezone(UTC),
        gross_cents=gross,
        net_cents=net,
        # price and gumroad_fee are in USD cents regardless of the listing currency
        currency="USD",
        status=_status(record),
        raw=record,
    )


def has_affiliate(record: dict[str, Any]) -> bool:
    return bool(record.get("affiliate"))
