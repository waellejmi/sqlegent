import json

from langgraph.types import Command

from agent.graph import agent


def handle_stream(stream_iterator):
    for step in stream_iterator:
        if "__interrupt__" in step:
            action = step["__interrupt__"][0]
            print(30 * "=")
            print("INTERRUPTED:")
            for request in action.value:
                print(json.dumps(request, indent=2))
        elif "messages" in step:
            step["messages"][-1].pretty_print()
        else:
            pass


def run_agent():
    question = "Which genre on average has the longest tracks?"
    config = {"configurable": {"thread_id": "1"}}

    print("--- Starting Agent ---")
    initial_stream = agent.stream(
        {"messages": [{"role": "user", "content": question}]},
        config,
        stream_mode="values",
    )
    handle_stream(initial_stream)
    print("\n--- Resuming Agent ---")

    # Resume Stream
    resume_stream = agent.stream(
        Command(resume={"type": "accept"}),
        # Command(resume={"type": "edit", "args": {"query": "SELECT * FROM ..."}}),
        # Command(resume={"type": "response", "args": {"This is wrong, I asked for something else ..."}),
        # Command(resume={"type": "reject"),
        config,
        stream_mode="values",
    )
    handle_stream(resume_stream)


if __name__ == "__main__":
    run_agent()
