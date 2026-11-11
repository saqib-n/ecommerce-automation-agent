"""Proactive low-stock check, meant to run on a schedule (cron, a GitHub
Action, an n8n trigger), not something a customer triggers by chatting.

This is the part of the project that's not just answering questions when
asked, it's the agent watching inventory on its own and telling a human
before a product actually runs out. Run it directly to see it work:

    python stock_monitor.py

If SLACK_WEBHOOK_URL is set in .env, it also posts the alert to Slack.
Without it, it just prints to the console, which is enough to see the
logic working without needing a Slack workspace set up.
"""

import os

import requests
from dotenv import load_dotenv

from agent.shopify_client import low_stock_items, store_name

load_dotenv()


def format_alert(items: list[dict], store: str) -> str:
    lines = [f"Low stock alert, {store}"]
    for item in items:
        lines.append(f"- {item['name']} ({item['sku']}): {item['stock_count']} left, threshold is {item['low_stock_threshold']}")
    return "\n".join(lines)


def send_to_slack(message: str) -> None:
    response = requests.post(os.environ["SLACK_WEBHOOK_URL"], json={"text": message}, timeout=15)
    response.raise_for_status()


def main():
    items = low_stock_items()

    if not items:
        print("No items below their low stock threshold. Nothing to alert on.")
        return

    message = format_alert(items, store_name())
    print(message)

    if os.getenv("SLACK_WEBHOOK_URL"):
        try:
            send_to_slack(message)
            print("\nAlert also posted to Slack.")
        except requests.RequestException as exc:
            print(f"\nCouldn't post to Slack: {exc}")
    else:
        print("\n(SLACK_WEBHOOK_URL not set, alert only printed here.)")


if __name__ == "__main__":
    main()
