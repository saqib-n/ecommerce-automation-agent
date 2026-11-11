from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage

from agent import graph
from agent.shopify_client import (
    check_return_eligibility, get_order, get_stock, low_stock_items, shopify_status,
)
from stock_monitor import format_alert


def no_shopify(monkeypatch):
    monkeypatch.delenv("SHOPIFY_STORE_URL", raising=False)
    monkeypatch.delenv("SHOPIFY_ACCESS_TOKEN", raising=False)


def test_stock_question_finds_the_product(monkeypatch):
    no_shopify(monkeypatch)
    matches = get_stock("is the wool throw blanket in stock?")
    assert [m["name"] for m in matches] == ["Cedar Wool Throw Blanket"]


def test_plural_and_unknown_products(monkeypatch):
    no_shopify(monkeypatch)
    assert [m["name"] for m in get_stock("do you have candles?")] == ["Cedar Soy Candle"]
    assert get_stock("do you sell bicycles?") == []


def test_return_rules(monkeypatch):
    no_shopify(monkeypatch)
    assert check_return_eligibility("ORD-3001")["eligible"] is True
    late = check_return_eligibility("ORD-3004")
    assert (late["reason"], late["days_since_order"]) == ("outside_return_window", 114)
    assert check_return_eligibility("ORD-3003")["reason"] == "not_yet_delivered"
    assert check_return_eligibility("ORD-9999")["reason"] == "order_not_found"


def test_demo_dates_are_relative(monkeypatch):
    no_shopify(monkeypatch)
    order = get_order("ord-3002")
    assert order["order_date"] < order["delivery_estimate"]


def test_shopify_status_mapping():
    assert shopify_status("fulfilled") == "Shipped"
    assert shopify_status(None) == "Processing"


def test_low_stock_alert(monkeypatch):
    no_shopify(monkeypatch)
    items = low_stock_items()
    assert {i["sku"] for i in items} == {"CEDAR-THROW-02", "CEDAR-CANDLE-03"}
    assert format_alert(items, "Cedar & Co.").startswith("Low stock alert, Cedar & Co.")


def test_classifier_routes_and_remembers_order_id(monkeypatch):
    no_shopify(monkeypatch)
    llm = GenericFakeChatModel(messages=iter([AIMessage(content="return_refund"), AIMessage(content="order_status")]))
    app = graph.build_graph(llm=llm)
    config = {"configurable": {"thread_id": "t1"}}
    first = app.invoke({"messages": [HumanMessage(content="I want to return ORD-3001")]}, config=config)
    assert first["category"] == "return_refund"
    assert "eligible for a return" in first["messages"][-1].text
    second = app.invoke({"messages": [HumanMessage(content="and where is it now?")]}, config=config)
    assert "ORD-3001" in second["messages"][-1].text


def test_unexpected_label_escalates():
    llm = GenericFakeChatModel(messages=iter([AIMessage(content="no idea")]))
    result = graph.classify_node({"messages": [HumanMessage(content="hmm")]}, llm)
    assert graph.route_after_classify(result) == "escalate"
