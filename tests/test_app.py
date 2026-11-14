from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

import app as web
from agent import graph


def test_dashboard_store_and_stock_monitor(monkeypatch):
    monkeypatch.delenv("SHOPIFY_STORE_URL", raising=False)
    monkeypatch.delenv("SHOPIFY_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    client = TestClient(web.app)

    assert "Run stock monitor" in client.get("/").text
    store = client.get("/api/store").json()
    assert store["name"] == "Cedar & Co." and len(store["products"]) == 4
    assert store["orders"][0]["order_date"] >= store["orders"][-1]["order_date"]

    check = client.post("/api/stock-check").json()
    assert {i["sku"] for i in check["items"]} == {"CEDAR-THROW-02", "CEDAR-CANDLE-03"}
    assert check["alert"].startswith("Low stock alert") and check["slack"] is None


def test_support_chat_routes_through_the_graph(monkeypatch):
    monkeypatch.delenv("SHOPIFY_STORE_URL", raising=False)
    monkeypatch.delenv("SHOPIFY_ACCESS_TOKEN", raising=False)
    llm = GenericFakeChatModel(messages=iter([AIMessage(content="order_status")]))
    monkeypatch.setattr(web, "_graph", graph.build_graph(llm=llm))
    client = TestClient(web.app)

    turn = client.post("/api/chat", json={"session_id": "s1", "text": "where is ORD-3002?"}).json()
    assert turn["category"] == "order_status" and turn["order_id"] == "ORD-3002"
    assert "ORD-3002" in turn["reply"]
    assert client.post("/api/chat", json={"session_id": "s1", "text": ""}).status_code == 422
