"""Common sale model shared by all marketplaces (see docs/PLAN.md)."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


class Status(StrEnum):
    SOLD = "sold"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"
    CHARGEBACK = "chargeback"


@dataclass(frozen=True)
class Sale:
    """One sale record. Money in integer minor units (cents) of `currency`, time in UTC.

    A record may cover several units (`quantity`, e.g. a Fab daily row) and may be negative
    (a Fab refund row); amounts are totals for the record.
    """

    marketplace: str
    external_id: str
    product_title: str | None
    product_ref: str | None
    sold_at: datetime
    gross_cents: int
    net_cents: int | None
    currency: str
    status: Status
    raw: dict[str, Any]
    quantity: int = 1
