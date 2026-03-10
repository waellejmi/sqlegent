import asyncio
import json
import logging
import readline
import uuid

from langchain_core.callbacks import UsageMetadataCallbackHandler
from langchain_core.messages import AIMessageChunk
from langgraph.types import Command

from agent.graph import agent

logging.basicConfig(level=logging.INFO, format=" %(levelname)s - %(message)s")


def display_streaming_content(content: str) -> None:
    print(content, end="", flush=True)


# FIX:fix prefilled text not working some environments (Different behavior of readline in Linux/Windows and terminal emulators )
# TODO: Implement direct input, for example press e to edit directly
async def get_user_input(interrupt_info) -> dict:
    print("\n" + "=" * 30)
    print("INTERRUPTED:")
    try:
        print(json.dumps(interrupt_info, indent=2))
    except TypeError:
        print(interrupt_info)

    prompt = "\nHow would you like to proceed? \n[a]ccept  [e]dit  [r]eject [f]eedback \nChoice: "
    choice = (await asyncio.to_thread(input, prompt)).strip().lower()

    if choice.startswith("e"):
        current_query = interrupt_info[0].get("args").get("query")

        def input_with_prefill(prompt, text):
            def hook():
                readline.insert_text(text)
                readline.redisplay()

            readline.set_pre_input_hook(hook)
            try:
                return input(prompt)
            finally:
                readline.set_pre_input_hook(None)

        new_query = await asyncio.to_thread(
            input_with_prefill, "Edit query: ", current_query
        )

        return {"type": "edit", "edited_query": new_query}

    elif choice.startswith("f"):
        feedback = await asyncio.to_thread(input, "Feedback for the agent: \n")
        return {"type": "response", "feedback": feedback}

    elif choice.startswith("r"):
        return {"type": "reject"}

    return {"type": "accept"}


async def run_agent(input_state: dict, config: dict):
    print("--- Starting Agent ---")

    while True:
        resume_required = False
        async for mode, chunk in agent.astream(
            input_state,
            stream_mode=["updates", "messages"],
            config=config,
        ):
            if mode == "messages":
                msg, _ = chunk
                if isinstance(msg, AIMessageChunk) and msg.content:
                    display_streaming_content(msg.content)
            if mode == "updates":
                if "__interrupt__" in chunk:
                    interrupt_info = chunk["__interrupt__"][0].value
                    user_response = await get_user_input(interrupt_info)
                    input_state = Command(resume=user_response)
                    resume_required = True
                    print("\n--- Resuming Agent ---")
                    break
                else:
                    current_node = next(iter(chunk.keys()), None)
                    if current_node:
                        print(f"\n[Transition] -> {current_node}")
        if not resume_required:
            break

    print("\n--- Full Node History ---")
    for i, state in enumerate(agent.get_state_history(config)):
        print(f"Checkpoint {i}: next={state.next} ")


if __name__ == "__main__":
    usage_callback = UsageMetadataCallbackHandler()
    config = {
        "configurable": {"thread_id": str(uuid.uuid4())},
        "callbacks": [usage_callback],
    }
    questions = {
        "success": "Which genre on average has the longest tracks?",
        "empty_result": "give me the names of all employees born after 1990-01-01",
        "skipped": "What is the airspeed velocity of an unladen swallow?",
        "complex1": "Which 5 artists generated the most revenue, and what is their total revenue and number of tracks sold?",
        "complex2": "Which customers spent more than the average customer spending, and what is their total amount spent?",
    }
    question = questions["complex1"]

    initial_state = {
        "messages": [{"role": "user", "content": question}],
        "user_question": question,
        "last_query": None,
        "previous_queries": [],
        "analysis_result": None,
        "retry_count": 0,
    }

    asyncio.run(run_agent(initial_state, config))

    print("\n--- Token Usage ---")
    print(usage_callback.usage_metadata)
