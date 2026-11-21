"""Cosmos (Leartes): shared core for both import paths (spec M4a).

A transaction comes from the browser agent (JSON the sales page loads from its own API) or, later,
from a pasted copy of the sales table. Either way it becomes a CosmosTransaction and then one
Sale per product. The payout is per transaction only, so it is split across products in proportion
to what was paid for each, to the cent.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from sales_tracker.models import Sale, Status

MARKETPLACE = "cosmos"
CURRENCY = "USD"
PAGE_PAUSE_SECONDS = 3.0
MAX_PAGES = 50
REFUND_WINDOW_DAYS = 30
NUMBER_RE = re.compile(r"^\d+(\.\d+)?$")


class SkipTransaction(Exception):
    """A transaction that cannot be mapped. Carries only its ID and a reason."""

    def __init__(self, tx_id: str | None, reason: str):
        super().__init__(f"{tx_id}: {reason}")
        self.tx_id = tx_id
        self.reason = reason


class FetchError(Exception):
    """Loading sales failed as a whole (unexpected response, too many pages). Nothing is saved."""


class SessionExpired(FetchError):
    """The browser profile is no longer logged in to Cosmos."""


@dataclass(frozen=True)
class CosmosItem:
    sku: str
    title: str | None
    amount_cents: int | None  # None when the source does not say (pasted table)
    quantity: int
    license: str | None


@dataclass(frozen=True)
class CosmosTransaction:
    id: str
    created_at: datetime
    virtual: bool
    amount_cents: int
    payout_cents: int | None  # None for Virtual Credits sales
    refunded: bool
    items: tuple[CosmosItem, ...]
    source: str
    raw: dict[str, Any]


def split_cents(total: int, weights: list[int]) -> list[int]:
    """Split total into parts proportional to weights; parts always sum to total (largest remainder)."""
    if not weights:
        return []
    if sum(weights) == 0:
        weights = [1] * len(weights)
    whole = sum(weights)
    floors = [total * w // whole for w in weights]
    remainders = [total * w % whole for w in weights]
    leftover = total - sum(floors)
    # stable: on equal remainders the earlier item gets the cent
    for index in sorted(range(len(weights)), key=lambda i: -remainders[i])[:leftover]:
        floors[index] += 1
    return floors


def _cents(value: Any, field: str, tx_id: str) -> int:
    text = str(value).strip() if value is not None else ""
    if not NUMBER_RE.match(text):
        raise SkipTransaction(tx_id, f"'{field}' není číslo: {text!r}")
    try:
        cents = Decimal(text) * 100
    except InvalidOperation:
        raise SkipTransaction(tx_id, f"'{field}' není číslo: {text!r}") from None
    if cents != cents.to_integral_value():
        raise SkipTransaction(tx_id, f"'{field}' má zlomek centu ({text}), nezaokrouhluji")
    return int(cents)


def _created_at(value: Any, tx_id: str) -> datetime:
    try:
        moment = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise SkipTransaction(tx_id, "'created_at' chybí nebo není čas ISO 8601") from None
    if moment.tzinfo is None:
        raise SkipTransaction(tx_id, "'created_at' nemá časovou zónu")
    return moment.astimezone(UTC)


def from_api(record: dict[str, Any], source: str = "browser") -> CosmosTransaction:
    """Validate one transaction from api.publisher.leartesstudios.com/sales (format: docs/ZDROJE.md)."""
    raw_id = record.get("id")
    if raw_id is None or isinstance(raw_id, bool) or str(raw_id).strip() == "":
        raise SkipTransaction(None, "chybí 'id'")
    tx_id = str(raw_id)

    if "created_at" not in record:
        raise SkipTransaction(tx_id, "chybí 'created_at'")
    created_at = _created_at(record["created_at"], tx_id)

    kind = record.get("type")
    if kind not in ("real", "virtual"):
        raise SkipTransaction(tx_id, f"neznámý 'type': {kind!r}")
    virtual = kind == "virtual"

    amount = _cents(record.get("raw_amount"), "raw_amount", tx_id)

    payout = record.get("payout")
    if payout is None:
        if not virtual:
            raise SkipTransaction(tx_id, "chybí 'payout'")
        payout_cents = None
    else:
        if not isinstance(payout, dict) or payout.get("currency") != CURRENCY:
            raise SkipTransaction(tx_id, f"'payout' není v {CURRENCY}")
        payout_cents = _cents(payout.get("amount"), "payout.amount", tx_id)

    raw_items = record.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise SkipTransaction(tx_id, "chybí 'items'")
    items = []
    for raw_item in raw_items:
        sku = raw_item.get("sku") if isinstance(raw_item, dict) else None
        if not isinstance(sku, str) or not sku.strip():
            raise SkipTransaction(tx_id, "produkt bez 'sku'")
        quantity = raw_item.get("quantity", 1)
        if type(quantity) is not int or quantity < 1:
            raise SkipTransaction(tx_id, f"'quantity' u {sku} není kladné celé číslo")
        items.append(CosmosItem(
            sku=sku.strip(),
            title=raw_item.get("title"),
            amount_cents=_cents(raw_item.get("amount"), f"items[{sku}].amount", tx_id),
            quantity=quantity,
            license=raw_item.get("license"),
        ))

    skus = [item.sku for item in items]
    if len(set(skus)) != len(skus):
        raise SkipTransaction(tx_id, "stejný produkt (sku) je v transakci dvakrát")
    if sum(item.amount_cents for item in items) != amount:
        raise SkipTransaction(tx_id, "součet částek produktů nesedí s 'raw_amount'")

    return CosmosTransaction(
        id=tx_id,
        created_at=created_at,
        virtual=virtual,
        amount_cents=amount,
        payout_cents=payout_cents,
        refunded=record.get("refund_details") is not None,
        items=tuple(items),
        source=source,
        raw=record,
    )


def to_sales(tx: CosmosTransaction) -> list[Sale]:
    """One Sale per product. The payout is split in proportion to what was paid for each product."""
    if any(item.amount_cents is None for item in tx.items):
        raise SkipTransaction(tx.id, "chybí částky jednotlivých produktů")
    gross = [item.amount_cents for item in tx.items]
    # Virtual Credits: the whole amount counts as payout (Vítek's decision 2026-11-21)
    net = gross if tx.payout_cents is None else split_cents(tx.payout_cents, gross)
    return [
        Sale(
            marketplace=MARKETPLACE,
            external_id=f"{tx.id}|{item.sku}",
            product_title=item.title,
            product_ref=item.sku,
            sold_at=tx.created_at,
            gross_cents=gross[index],
            net_cents=net[index],
            currency=CURRENCY,
            status=Status.REFUNDED if tx.refunded else Status.SOLD,
            raw={"transaction": tx.raw, "source": tx.source, "item_index": index},
            quantity=item.quantity,
        )
        for index, item in enumerate(tx.items)
    ]


def _check_page(page: Any, number: int) -> tuple[list[dict], int]:
    if not isinstance(page, dict) or not isinstance(page.get("data"), list):
        raise FetchError("neočekávaný tvar odpovědi Cosmosu (chybí 'data')")
    meta = page.get("meta")
    if not isinstance(meta, dict):
        raise FetchError("neočekávaný tvar odpovědi Cosmosu (chybí 'meta')")
    current, last = meta.get("currentPage"), meta.get("lastPage")
    if type(current) is not int or type(last) is not int:
        raise FetchError("neočekávaný tvar odpovědi Cosmosu ('meta' bez čísel stránek)")
    if current != number:
        raise FetchError(f"Cosmos vrátil stránku {current} místo {number}")
    return page["data"], last


def _oldest(records: list[dict]) -> datetime | None:
    moments = []
    for record in records:
        try:
            moments.append(_created_at(record.get("created_at"), str(record.get("id"))))
        except SkipTransaction:
            return None  # unknown age → do not stop early
    return min(moments) if moments else None


def fetch_pages(
    load_page: Callable[[int], Any],
    known_ids: set[str],
    *,
    now: datetime,
    sleep: Callable[[float], None],
    max_pages: int = MAX_PAGES,
) -> list[dict]:
    """Raw transaction records, newest first.

    Goes on to the next page until the last page, or until a page holds only transactions already
    in the database that are all older than the refund window (so refunds of recent sales are seen).
    """
    records: list[dict] = []
    cutoff = now - timedelta(days=REFUND_WINDOW_DAYS)
    number = 1
    while True:
        data, last = _check_page(load_page(number), number)
        records.extend(data)
        if number >= last:
            return records
        oldest = _oldest(data)
        all_known = all(str(r.get("id")) in known_ids for r in data)
        if data and all_known and oldest is not None and oldest < cutoff:
            return records
        if number >= max_pages:
            raise FetchError(f"víc než {max_pages} stránek, zastaveno pro jistotu")
        number += 1
        sleep(PAGE_PAUSE_SECONDS)
