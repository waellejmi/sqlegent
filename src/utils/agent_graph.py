import pathlib
import sys

# from IPython.display import Image, display
# from langchain_core.runnables.graph import CurveStyle, MermaidDrawMethod, NodeStyles

project_root_dir = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root_dir))
from llm import agent

print(agent.get_graph().draw_mermaid())
# display(Image(agent.get_graph().draw_mermaid_png()))
