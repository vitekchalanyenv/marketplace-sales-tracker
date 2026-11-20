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
    """One sale. Money in integer minor units (cents) of `currency`, time in UTC."""

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
