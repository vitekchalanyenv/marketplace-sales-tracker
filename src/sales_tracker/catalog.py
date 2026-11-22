"""Product catalog: which listings on which marketplaces are the same product (spec M2).

Matching is exact only (ref, then normalized title). Similarity is used solely to *suggest*
a product for an unmatched listing; a wrong automatic match would silently distort the numbers.
"""

import difflib
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import yaml

MARKETPLACES = ("gumroad", "fab", "cosmos", "cgtrader")
KEY_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
SUGGEST_CUTOFF = 0.6


class CatalogError(Exception):
    def __init__(self, errors: list[str]):
        super().__init__("\n".join(errors))
        self.errors = errors


def normalize_title(title: str) -> str:
    return " ".join(title.split()).casefold()


@dataclass(frozen=True)
class Listing:
    marketplace: str
    ref: str | None
    title: str | None
    price_cents: int | None = None  # list price; only used to split pasted Cosmos transactions


@dataclass(frozen=True)
class Product:
    key: str
    name: str
    listings: tuple[Listing, ...]


class Catalog:
    def __init__(self, products: list[Product]):
        self.products = products
        self._by_ref: dict[tuple[str, str], str] = {}
        self._by_title: dict[tuple[str, str], str] = {}
        self._names = {p.key: p.name for p in products}
        self._prices: dict[tuple[str, str], int] = {}
        for product in products:
            for listing in product.listings:
                if listing.ref is not None:
                    self._by_ref[(listing.marketplace, listing.ref)] = product.key
                    if listing.price_cents is not None:
                        self._prices[(listing.marketplace, listing.ref)] = listing.price_cents
                if listing.title is not None:
                    self._by_title[(listing.marketplace, normalize_title(listing.title))] = product.key

    def name_of(self, key: str) -> str:
        return self._names[key]

    def price(self, marketplace: str, ref: str) -> int | None:
        """List price in cents of the listing with this ref, if the catalog gives one."""
        return self._prices.get((marketplace, ref))

    def match(self, marketplace: str, ref: str | None, title: str | None) -> str | None:
        if ref is not None and (marketplace, ref) in self._by_ref:
            return self._by_ref[(marketplace, ref)]
        if title is not None:
            return self._by_title.get((marketplace, normalize_title(title)))
        return None

    def suggest(self, title: str | None) -> str | None:
        """Most similar product (by product name or any listing title), or None. Never used to match."""
        if not title:
            return None
        candidates: dict[str, str] = {}
        for product in self.products:
            candidates[normalize_title(product.name)] = product.key
            for listing in product.listings:
                if listing.title:
                    candidates[normalize_title(listing.title)] = product.key
        best = difflib.get_close_matches(normalize_title(title), candidates, n=1, cutoff=SUGGEST_CUTOFF)
        return candidates[best[0]] if best else None


def _text(value: Any) -> str | None:
    """Non-empty string; integers (numeric IDs) are accepted as text."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _price(value: Any) -> int | None:
    """Positive amount with at most 2 decimals ('19.90' or 19.9) in cents, else None."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        cents = Decimal(str(value).strip()) * 100
    except InvalidOperation:
        return None
    if cents <= 0 or cents != cents.to_integral_value():
        return None
    return int(cents)


def _parse_product(index: int, raw: Any, errors: list[str]) -> Product | None:
    where = f"produkt č. {index + 1}"
    if not isinstance(raw, dict):
        errors.append(f"{where}: musí být slovník s 'key', 'name' a 'listings'")
        return None

    key = raw.get("key")
    if isinstance(key, str) and KEY_RE.match(key):
        where = f"{where} '{key}'"
    else:
        errors.append(f"{where}: 'key' chybí nebo není ve tvaru malá písmena, číslice a pomlčky (např. medieval-village)")
        key = None

    name = _text(raw.get("name"))
    if name is None:
        errors.append(f"{where}: chybí 'name'")

    listings: list[Listing] = []
    raw_listings = raw.get("listings")
    if not isinstance(raw_listings, dict) or not raw_listings:
        errors.append(f"{where}: 'listings' musí obsahovat aspoň jeden marketplace")
        raw_listings = {}
    for marketplace, items in raw_listings.items():
        if marketplace not in MARKETPLACES:
            errors.append(f"{where}: neznámý marketplace '{marketplace}' (povolené: {', '.join(MARKETPLACES)})")
            continue
        if not isinstance(items, list) or not items:
            errors.append(f"{where}, {marketplace}: musí být seznam listingů (- ref: … / - title: …)")
            continue
        for item in items:
            if not isinstance(item, dict) or set(item) - {"ref", "title", "price"}:
                errors.append(
                    f"{where}, {marketplace}: listing smí mít jen 'ref', 'title' a 'price', je tam {item!r}"
                )
                continue
            ref, title = _text(item.get("ref")), _text(item.get("title"))
            if ref is None and title is None:
                errors.append(f"{where}, {marketplace}: listing potřebuje neprázdný 'ref' nebo 'title'")
                continue
            price = None
            if "price" in item:
                price = _price(item["price"])
                if price is None:
                    errors.append(
                        f"{where}, {marketplace}: 'price' musí být kladná částka s nejvýš 2 desetinnými "
                        f"místy (např. 19.90), je tam {item['price']!r}"
                    )
                    continue
                if ref is None:
                    errors.append(f"{where}, {marketplace}: 'price' jde jen k listingu s 'ref'")
                    continue
            listings.append(Listing(marketplace, ref, title, price))

    if key is None or name is None:
        return None
    return Product(key, name, tuple(listings))


def _check_unique(products: list[Product], errors: list[str]) -> None:
    seen_keys: set[str] = set()
    for product in products:
        if product.key in seen_keys:
            errors.append(f"'{product.key}': stejný key je v katalogu dvakrát")
        seen_keys.add(product.key)

    owners: dict[tuple[str, str, str], str] = {}
    for product in products:
        for listing in product.listings:
            identities = []
            if listing.ref is not None:
                identities.append(("ref", listing.ref, listing.ref))
            if listing.title is not None:
                identities.append(("title", normalize_title(listing.title), listing.title))
            for kind, value, shown in identities:
                owner = owners.setdefault((listing.marketplace, kind, value), product.key)
                if owner != product.key:
                    errors.append(
                        f"{listing.marketplace}: {kind} '{shown}' je u dvou produktů "
                        f"('{owner}' a '{product.key}'), párování by nebylo jednoznačné"
                    )


def load_catalog(path: Path) -> Catalog:
    """Load and validate. Raises FileNotFoundError, or CatalogError with every problem found."""
    text = Path(path).read_text(encoding="utf-8")
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        line = f"řádek {mark.line + 1}: " if mark is not None else ""
        problem = getattr(exc, "problem", None) or str(exc)
        raise CatalogError([f"neplatné YAML – {line}{problem}"]) from None

    if not isinstance(data, dict) or not isinstance(data.get("products"), list):
        raise CatalogError(["katalog musí začínat 'products:' a pod ním seznam produktů"])

    errors: list[str] = []
    products = [
        product
        for index, raw in enumerate(data["products"])
        if (product := _parse_product(index, raw, errors)) is not None
    ]
    _check_unique(products, errors)
    if errors:
        raise CatalogError(errors)
    return Catalog(products)
