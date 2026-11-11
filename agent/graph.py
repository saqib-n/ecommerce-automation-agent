"""LangGraph router for the e-commerce support agent.

Same shape as the multi-agent-customer-support project, a classify step
routes to one specialist, but the specialists here read from
shopify_client.py, which is wired for a real Shopify store, not just mock
data. Order status and stock questions get answered from real inventory,
return eligibility is checked against the store's actual policy, and
anything else gets escalated with a ticket instead of guessed at.
"""

import random
import re
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AIMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages

from agent.llm import get_llm
from agent.shopify_client import check_return_eligibility, get_order, get_stock
ORDER_ID_RE = re.compile(r"\bORD-\d{3,6}\b", re.IGNORECASE)


class SupportState(TypedDict):
    messages: Annotated[list, add_messages]
    category: str
    order_id: str | None


def classify_node(state: SupportState, llm) -> dict:
    last_user_msg = state["messages"][-1].content

    order_id_match = ORDER_ID_RE.search(last_user_msg)
    order_id = order_id_match.group(0).upper() if order_id_match else state.get("order_id")

    system = SystemMessage(content=(
        "You are a routing classifier for an e-commerce store's support agent. "
        "Classify the customer's latest message into exactly one category:\n"
        "- order_status: asking where an order is or its delivery status\n"
        "- stock_check: asking if a product is in stock or available\n"
        "- return_refund: asking to return an item or get a refund\n"
        "- other: complaints, damaged items, or anything you can't confidently classify\n"
        "Reply with ONLY the single category word, nothing else."
    ))
    response = llm.invoke([system, *state["messages"]])
    category = response.text.strip().strip(".'\"").lower()
    if category not in {"order_status", "stock_check", "return_refund", "other"}:
        category = "other"

    return {"category": category, "order_id": order_id}


def order_status_node(state: SupportState) -> dict:
    order_id = state.get("order_id")
    if not order_id:
        return {"messages": [AIMessage(content="Happy to check that, what's your order ID?")]}

    order = get_order(order_id)
    if order is None:
        reply = f"I couldn't find an order with ID {order_id}. Could you double check it?"
    else:
        items = ", ".join(order["items"])
        reply = f"Order {order_id} ({items}) is currently {order['status']}."
    return {"messages": [AIMessage(content=reply)]}


def stock_check_node(state: SupportState) -> dict:
    query = state["messages"][-1].content
    matches = get_stock(query)

    if not matches:
        reply = "I couldn't find a matching product, could you tell me the exact product name?"
    else:
        lines = [f"{m['name']}: {'In stock' if m['stock_count'] > 0 else 'Out of stock'} ({m['stock_count']} left)" for m in matches]
        reply = "\n".join(lines)
    return {"messages": [AIMessage(content=reply)]}


def return_refund_node(state: SupportState) -> dict:
    order_id = state.get("order_id")
    if not order_id:
        return {"messages": [AIMessage(content="I can help with that, what's your order ID?")]}

    result = check_return_eligibility(order_id)

    if result["eligible"]:
        reply = (
            f"Order {result['order_id']} is eligible for a return, total refund would be "
            f"${result['amount']:.2f}. Our team will email you a prepaid return label."
        )
    elif result["reason"] == "order_not_found":
        reply = f"I couldn't find an order with ID {result['order_id']}."
    elif result["reason"] == "not_yet_delivered":
        reply = f"Order {result['order_id']} is still '{result['status']}', so it can't be returned until it arrives."
    else:
        reply = (
            f"Order {result['order_id']} was placed {result['days_since_order']} days ago, "
            f"which is outside our {result['window_days']}-day return window. "
            "I'll escalate this in case an exception applies."
        )
    return {"messages": [AIMessage(content=reply)]}


def escalate_node(state: SupportState) -> dict:
    ticket_id = f"ECM-{random.randint(10000, 99999)}"
    reply = f"I've escalated this to our support team, ticket {ticket_id} created, someone will follow up shortly."
    return {"messages": [AIMessage(content=reply)]}


def route_after_classify(state: SupportState) -> Literal["order_status", "stock_check", "return_refund", "escalate"]:
    return {
        "order_status": "order_status",
        "stock_check": "stock_check",
        "return_refund": "return_refund",
        "other": "escalate",
    }[state["category"]]


def build_graph(model: str | None = None, llm=None):
    llm = llm or get_llm(model)

    graph = StateGraph(SupportState)
    graph.add_node("classify", lambda state: classify_node(state, llm))
    graph.add_node("order_status", order_status_node)
    graph.add_node("stock_check", stock_check_node)
    graph.add_node("return_refund", return_refund_node)
    graph.add_node("escalate", escalate_node)

    graph.add_edge(START, "classify")
    graph.add_conditional_edges("classify", route_after_classify)
    graph.add_edge("order_status", END)
    graph.add_edge("stock_check", END)
    graph.add_edge("return_refund", END)
    graph.add_edge("escalate", END)

    return graph.compile(checkpointer=MemorySaver())
