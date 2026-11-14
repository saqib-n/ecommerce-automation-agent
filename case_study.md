# E-commerce Order and Inventory Agent

## Portfolio entry

Two automations for an online store in one project. A support agent that answers order status, stock and return questions from live store data and checks returns against the shop's actual policy before approving anything. And a separate scheduled job that watches inventory on its own and raises a low-stock alert before a product runs out, with no customer involved. Written against the real Shopify Admin API with a local data fallback, so it demos with no store account and connects to a live shop with two environment variables.

**Stack:** Python, LangGraph, Shopify Admin API, Slack

---

## Two problems, deliberately kept apart

Order status and return questions are most of a small store's support volume, and they're the most repetitive part of the job.

Running out of a popular item without warning is a different problem entirely. It costs sales, nobody asks a question that would surface it, and in most small shops someone just notices a few days late.

These get solved differently. One is a conversation. The other is a cron job. Building them as one thing would have made both worse, so the support chat (`chat_cli.py`, and the `app.py` dashboard) and `stock_monitor.py` are separate entry points sharing a data layer.

The second one is also the more interesting demo. An agent that answers questions is expected now. An agent that noticed something and told you first lands differently in a client call.

## Policy as configuration

`data/store_policy.json` holds the return window and which order statuses can be returned. Not the code.

Every shop's policy is a bit different, 14 days here, 30 there, final-sale exclusions somewhere else. If that lives in the agent logic, every new client is a development task for something that isn't a development problem. Pulling it into a file means onboarding a shop is data entry.

Same reasoning as the scoring rubric in my lead qualification project. It's the pattern I reach for whenever a business rule is going to differ per client.

## A real integration detail worth mentioning

Shopify has no per-product low stock threshold. The local data file does, because that's what a shop owner actually wants, different reorder points for a $12 mug and a $65 blanket.

So when a real store is connected, the monitor falls back to one threshold across all products, and the README says so plainly. On a real build I'd store per-product thresholds in Shopify metafields. Pretending the mismatch doesn't exist would have been the easier README to write and the worse thing to hand a client.

## Not finished

The monitor is a script you run. It needs to be on a schedule, cron, a GitHub Action, or an n8n trigger, and until it is, the proactive half only half works.

Beyond that: WooCommerce as a second backend, letting the agent actually create the return in Shopify once it's approved rather than only telling the customer, and order lookup by email for customers who don't have their order ID handy.

## My part

The split between the reactive and proactive halves, the Shopify-backed data layer with its fallback, and the routing and return-eligibility logic.
