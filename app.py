"""Store admin dashboard for the e-commerce agent.

Opens a store-admin style page in the browser with both halves of the
project side by side:

  - the support chat, where the LangGraph router answers customers from
    real order and stock data (same graph as chat_cli.py)
  - the stock monitor, the proactive low-stock check from stock_monitor.py

Data comes from Shopify when SHOPIFY_STORE_URL and SHOPIFY_ACCESS_TOKEN are
set, otherwise from the demo files in data/.

Run:
    python app.py
"""

import logging
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

import stock_monitor
from agent.graph import build_graph
from agent.llm import DEFAULT_MODEL
from agent.shopify_client import _load, _shopify_configured, list_products, low_stock_items, recent_orders, store_name

load_dotenv()

logger = logging.getLogger("ecommerce-agent")
app = FastAPI(title="E-commerce Order and Inventory Agent")
WEB_DIR = Path(__file__).resolve().parent / "web"
_graph = None


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=64)
    text: str = Field(min_length=1, max_length=2000)


def support_turn(session_id: str, text: str) -> dict:
    """One customer message through the router graph. The session id is the
    conversation thread, so an order ID given earlier is remembered."""
    global _graph
    if _graph is None:
        _graph = build_graph()
    config = {"configurable": {"thread_id": f"web-{session_id}"}}
    result = _graph.invoke({"messages": [HumanMessage(content=text)]}, config=config)
    return {"reply": result["messages"][-1].text, "category": result.get("category"), "order_id": result.get("order_id")}


@app.get("/", include_in_schema=False)
def dashboard():
    return FileResponse(WEB_DIR / "index.html")


@app.get("/api/info")
def info():
    return {"model": os.getenv("LLM_MODEL") or DEFAULT_MODEL, "source": "Shopify" if _shopify_configured() else "Demo data (data/*.json)"}


@app.get("/api/store")
def store():
    return {"name": store_name(), "policy": _load("store_policy.json"), "products": list_products(), "orders": recent_orders()}


@app.post("/api/chat")
def chat(request: ChatRequest):
    started = time.perf_counter()
    try:
        turn = support_turn(request.session_id, request.text.strip())
    except Exception as exc:
        logger.exception("Support chat failed")
        detail = str(exc).splitlines()[0][:200] if str(exc) else ""
        return JSONResponse(status_code=502, content={"error": f"The agent could not answer ({type(exc).__name__}: {detail})."})
    return {**turn, "seconds": round(time.perf_counter() - started, 1)}


@app.post("/api/stock-check")
def stock_check():
    """Run the scheduled low-stock check now. No model involved."""
    items = low_stock_items()
    if not items:
        return {"items": [], "alert": None, "slack": None}
    alert = stock_monitor.format_alert(items, store_name())
    slack = None
    if os.getenv("SLACK_WEBHOOK_URL"):
        try:
            stock_monitor.send_to_slack(alert)
            slack = "posted to Slack"
        except Exception as exc:
            slack = f"Slack post failed: {type(exc).__name__}"
    return {"items": items, "alert": alert, "slack": slack}


if __name__ == "__main__":
    import threading
    import webbrowser

    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    threading.Timer(1.5, lambda: webbrowser.open(f"http://localhost:{port}")).start()
    uvicorn.run(app, host="127.0.0.1", port=port)
