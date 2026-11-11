"""CLI demo for the e-commerce support agent.

Run:
    python app.py

Try:
    is the wool throw blanket in stock?
    where's my order ORD-3002?
    I want to return ORD-3004
    my order came broken, this is unacceptable
"""

import uuid

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage

from agent.graph import build_graph

load_dotenv()


def main():
    graph = build_graph()
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    print("Cedar & Co. Support Agent - type 'exit' to quit\n")

    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in {"exit", "quit"}:
            break
        if not user_input:
            continue

        result = graph.invoke({"messages": [HumanMessage(content=user_input)]}, config=config)
        reply = result["messages"][-1].text
        category = result.get("category", "?")
        print(f"Agent [{category}]: {reply}\n")


if __name__ == "__main__":
    main()
