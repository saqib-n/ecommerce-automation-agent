"""Store data access layer.

Every function here tries the real Shopify Admin API first if store
credentials are set in the environment, and falls back to the local JSON
files in data/ otherwise. That fallback is what lets this whole project
run and demo with zero store account needed, swap it out for a real
WooCommerce or other platform client the same way for a different client.
"""

import json
import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DEFAULT_SHOPIFY_API_VERSION = "2026-04"

# Shopify reports fulfillment, not delivery. Map it onto the statuses the
# return policy in data/store_policy.json is written against.
SHOPIFY_STATUS = {"fulfilled": "Shipped", "partial": "Partially shipped", "restocked": "Returned"}

# Words that say nothing about which product someone means.
STOPWORDS = {
    "the", "and", "for", "you", "your", "are", "any", "have", "has", "got", "get", "can",
    "does", "did", "still", "stock", "available", "availability", "left", "there", "how",
    "many", "much", "what", "about", "with", "want", "need", "buy", "order", "item", "items",
    "product", "products", "this", "that", "please", "know", "tell",
}


def _load(filename: str):
    with open(DATA_DIR / filename, "r", encoding="utf-8") as f:
        return json.load(f)


def _mock_orders() -> dict:
    """Demo orders store their dates relative to today, so the return window
    examples in the README behave the same whenever someone runs this."""
    today = date.today()
    orders = {}
    for order_id, raw in _load("orders.json").items():
        order = dict(raw)
        placed = today - timedelta(days=order.pop("ordered_days_ago"))
        order["order_date"] = placed.isoformat()
        order["delivery_estimate"] = (placed + timedelta(days=order.pop("delivery_days"))).isoformat()
        orders[order_id] = order
    return orders


def _shopify_configured() -> bool:
    return bool(os.getenv("SHOPIFY_STORE_URL") and os.getenv("SHOPIFY_ACCESS_TOKEN"))


def _shopify_url(resource: str) -> str:
    store = os.environ["SHOPIFY_STORE_URL"].strip().removeprefix("https://").removeprefix("http://").rstrip("/")
    version = os.getenv("SHOPIFY_API_VERSION") or DEFAULT_SHOPIFY_API_VERSION
    return f"https://{store}/admin/api/{version}/{resource}.json"


def _shopify_get(resource: str, params: dict | None = None) -> dict:
    headers = {"X-Shopify-Access-Token": os.environ["SHOPIFY_ACCESS_TOKEN"]}
    response = requests.get(_shopify_url(resource), headers=headers, params=params, timeout=15)
    response.raise_for_status()
    return response.json()


def shopify_status(fulfillment_status: str | None) -> str:
    return SHOPIFY_STATUS.get(fulfillment_status or "", "Processing")


def _terms(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    terms = set()
    for word in words:
        if len(word) < 3 or word in STOPWORDS:
            continue
        # crude plural handling, "candles" should find "Candle"
        terms.add(word[:-1] if len(word) > 3 and word.endswith("s") and not word.endswith("ss") else word)
    return terms


def _best_matches(query: str, products: list[dict]) -> list[dict]:
    """Products whose name shares the most words with the customer's message.

    The message is a whole sentence ("is the wool throw blanket in stock?"),
    so matching it as a substring of a product name never works.
    """
    query_terms = _terms(query)
    scored = [(len(query_terms & _terms(p["name"])), p) for p in products]
    best = max((score for score, _ in scored), default=0)
    return [p for score, p in scored if score == best and best > 0]


def get_order(order_id: str) -> dict | None:
    """Look up an order. Tries the real Shopify Admin API if configured,
    otherwise reads data/orders.json."""
    order_id = order_id.strip().upper()

    if _shopify_configured():
        orders = _shopify_get("orders", {"name": order_id, "status": "any"}).get("orders", [])
        if not orders:
            return None
        order = orders[0]
        return {
            "customer": (order.get("customer") or {}).get("first_name", "customer"),
            "items": [line["title"] for line in order.get("line_items", [])],
            "status": shopify_status(order.get("fulfillment_status")),
            "order_date": order.get("created_at", "")[:10],
            "amount": float(order.get("total_price", 0)),
        }

    return _mock_orders().get(order_id)


def _all_products() -> list[dict]:
    if _shopify_configured():
        products = _shopify_get("products", {"limit": 250}).get("products", [])
        return [
            {
                "sku": p.get("handle", str(p.get("id", ""))),
                "name": p["title"],
                "stock_count": sum(v.get("inventory_quantity", 0) for v in p.get("variants", [])),
            }
            for p in products
        ]
    return [{"sku": sku, **item} for sku, item in _load("inventory.json").items()]


def get_stock(query: str) -> list[dict]:
    """Find the product(s) a customer is asking about, from Shopify if
    configured, otherwise from data/inventory.json."""
    return _best_matches(query, _all_products())


def check_return_eligibility(order_id: str) -> dict:
    """Evaluate whether an order is eligible for a return under the
    store's policy (data/store_policy.json)."""
    order = get_order(order_id)
    if order is None:
        return {"eligible": False, "reason": "order_not_found", "order_id": order_id}

    policy = _load("store_policy.json")

    if order["status"] not in policy["returnable_statuses"]:
        return {"eligible": False, "reason": "not_yet_delivered", "order_id": order_id, "status": order["status"]}

    order_date = datetime.strptime(order["order_date"], "%Y-%m-%d").date()
    days_since_order = (date.today() - order_date).days

    if days_since_order > policy["return_window_days"]:
        return {
            "eligible": False,
            "reason": "outside_return_window",
            "order_id": order_id,
            "days_since_order": days_since_order,
            "window_days": policy["return_window_days"],
        }

    return {"eligible": True, "order_id": order_id, "amount": order["amount"]}


def low_stock_items(default_threshold: int = 10) -> list[dict]:
    """Every item at or below its restock threshold. Used by stock_monitor.py.

    Shopify has no concept of a per-product low stock threshold, so when a
    real store is connected we fall back to default_threshold for every
    product. The local inventory file carries a per-item threshold instead,
    which is closer to what a store owner actually wants.
    """
    if _shopify_configured():
        return [
            {**p, "low_stock_threshold": default_threshold}
            for p in _all_products()
            if p["stock_count"] <= default_threshold
        ]

    return [p for p in _all_products() if p["stock_count"] <= p["low_stock_threshold"]]


def store_name() -> str:
    return _load("store_policy.json").get("store_name", "the store")
