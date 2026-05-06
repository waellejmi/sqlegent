import asyncio
import json
import readline
from typing import Any

NODE_FRIENDLY_NAMES = {
    "chat": "Thinking...",
    "tools": "Querying Database...",
    "question_synthesis": "Synthesizing Question...",
    "list_tables": "Viewing Tables...",
    "retrieve_context": "Retrieving Context...",
    "skip_pipeline": "Checking Requirements...",
    "call_get_schema": "Selecting Tables...",
    "get_schema": "Getting Schemas...",
    "generate_query": "Generating Query...",
    "run_query": "Executing Query...",
    "analyze_result": "Analyzing Result...",
    "explain_result": "Formatting Result...",
}


def display_streaming_content(content: str) -> None:
    print(content, end="", flush=True)


def display_transition(node_name: str) -> None:
    friendly_name = NODE_FRIENDLY_NAMES.get(node_name)
    if friendly_name:
        print(f"\n[ {friendly_name} ]", flush=True)


async def get_user_interrupt_response(interrupt_info: Any) -> dict[str, Any]:
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

        def input_with_prefill(local_prompt: str, text: str):
            def hook():
                readline.insert_text(text)
                readline.redisplay()

            readline.set_pre_input_hook(hook)
            try:
                return input(local_prompt)
            finally:
                readline.set_pre_input_hook(None)

        new_query = await asyncio.to_thread(
            input_with_prefill, "Edit query: ", current_query
        )
        return {"type": "edit", "edited_query": new_query}

    if choice.startswith("f"):
        feedback = await asyncio.to_thread(input, "Feedback for the agent: \n")
        return {"type": "response", "feedback": feedback}

    if choice.startswith("r"):
        return {"type": "reject"}

    return {"type": "accept"}
