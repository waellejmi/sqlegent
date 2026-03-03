import asyncio
import json
import uuid

from langchain_core.callbacks import UsageMetadataCallbackHandler
from langchain_core.messages import AIMessageChunk
from langgraph.types import Command

from agent.graph import agent


def display_streaming_content(content: str) -> None:
    print(content, end="", flush=True)


async def get_user_input(interrupt_info) -> dict:
    print("\n" + "=" * 30)
    print("INTERRUPTED:")
    try:
        print(json.dumps(interrupt_info, indent=2))
    except TypeError:
        print(interrupt_info)

    prompt = "\nHow would you like to proceed?\n[a]ccept  [e]dit  [r]eject\nChoice: "
    choice = (await asyncio.to_thread(input, prompt)).strip().lower()

    if choice.startswith("e"):
        new_query = await asyncio.to_thread(input, "New query: ")
        return {"type": "edit", "args": {"query": new_query}}
    if choice.startswith("r"):
        return {"type": "reject"}
    return {"type": "accept"}


async def run_agent(question: str, config: dict):
    print("--- Starting Agent ---")
    next_input = {"messages": [{"role": "user", "content": question}]}

    while True:
        resume_required = False
        async for _, mode, chunk in agent.astream(
            next_input,
            stream_mode=["messages", "updates"],
            config=config,
        ):
            if mode == "messages":
                msg, _ = chunk
                if isinstance(msg, AIMessageChunk) and msg.content:
                    display_streaming_content(msg.content)
            elif mode == "updates":
                if "__interrupt__" in chunk:
                    interrupt_info = chunk["__interrupt__"][0].value
                    user_response = await get_user_input(interrupt_info)
                    next_input = Command(resume=user_response)
                    resume_required = True
                    print("\n--- Resuming Agent ---")
                    break
                else:
                    current_node = next(iter(chunk.keys()), None)
                    if current_node:
                        print(f"\n[Transition] -> {current_node}")
        if not resume_required:
            break


if __name__ == "__main__":
    question = "Which genre on average has the longest tracks?"
    usage_callback = UsageMetadataCallbackHandler()
    config = {
        "configurable": {"thread_id": str(uuid.uuid4())},
        "callbacks": [usage_callback],
    }
    asyncio.run(run_agent(question, config))

    print("\n--- Token Usage ---")
    print(usage_callback.usage_metadata)
