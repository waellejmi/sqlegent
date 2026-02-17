import pathlib
from typing import Callable, NotRequired, TypedDict

from langchain.agents import create_agent
from langchain.agents.middleware import (
    AgentMiddleware,
    AgentState,
    HumanInTheLoopMiddleware,
    ModelRequest,
    ModelResponse,
)
from langchain.messages import SystemMessage, ToolMessage
from langchain.tools import ToolRuntime, tool
from langchain_groq import ChatGroq
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command, interrupt

from utils.env_config import MyConfig

config = MyConfig()
project_root = pathlib.Path(__file__).resolve().parent.parent
db_path = project_root / "data" / "Chinook.db"

model = ChatGroq(
    model="qwen/qwen3-32b",
    api_key=config.LLM_API_KEY,
    temperature=0,
    max_tokens=None,
    reasoning_format="parsed",
    timeout=None,
    max_retries=2,
)


class SkillState(AgentState):
    skills_loaded: NotRequired[list[str]]


class Skill(TypedDict):
    name: str
    description: str
    content: str


SKILLS: list[Skill] = [
    {
        "name": "sales_analytics",
        "description": "Database schema and business logic for sales data analysis including customers, orders, and revenue.",
        "content": """
# Sales Analytics Schema

## Tables

### customers
- customer_id (PRIMARY KEY)
- name
- email
- signup_date
- status (active/inactive)
- customer_tier (bronze/silver/gold/platinum)

### orders
- order_id (PRIMARY KEY)
- customer_id (FOREIGN KEY -> customers)
- order_date
- status (pending/completed/cancelled/refunded)
- total_amount
- sales_region (north/south/east/west)

### order_items
- item_id (PRIMARY KEY)
- order_id (FOREIGN KEY -> orders)
- product_id
- quantity
- unit_price
- discount_percent

## Business Logic

**Active customers**: status = 'active' AND signup_date <= CURRENT_DATE - INTERVAL '90 days'

**Revenue calculation**: Only count orders with status = 'completed'. Use total_amount from orders table, which already accounts for discounts.

**Customer lifetime value (CLV)**: Sum of all completed order amounts for a customer.

**High-value orders**: Orders with total_amount > 1000

## Example Query

-- Get top 10 customers by revenue in the last quarter
SELECT
    c.customer_id,
    c.name,
    c.customer_tier,
    SUM(o.total_amount) as total_revenue
FROM customers c
JOIN orders o ON c.customer_id = o.customer_id
WHERE o.status = 'completed'
  AND o.order_date >= CURRENT_DATE - INTERVAL '3 months'
GROUP BY c.customer_id, c.name, c.customer_tier
ORDER BY total_revenue DESC
LIMIT 10;
""",
    },
    {
        "name": "inventory_management",
        "description": "Database schema and business logic for inventory tracking including products, warehouses, and stock levels.",
        "content": """
# Inventory Management Schema

## Tables

### products
- product_id (PRIMARY KEY)
- product_name
- sku
- category
- unit_cost
- reorder_point (minimum stock level before reordering)
- discontinued (boolean)

### warehouses
- warehouse_id (PRIMARY KEY)
- warehouse_name
- location
- capacity

### inventory
- inventory_id (PRIMARY KEY)
- product_id (FOREIGN KEY -> products)
- warehouse_id (FOREIGN KEY -> warehouses)
- quantity_on_hand
- last_updated

### stock_movements
- movement_id (PRIMARY KEY)
- product_id (FOREIGN KEY -> products)
- warehouse_id (FOREIGN KEY -> warehouses)
- movement_type (inbound/outbound/transfer/adjustment)
- quantity (positive for inbound, negative for outbound)
- movement_date
- reference_number

## Business Logic

**Available stock**: quantity_on_hand from inventory table where quantity_on_hand > 0

**Products needing reorder**: Products where total quantity_on_hand across all warehouses is less than or equal to the product's reorder_point

**Active products only**: Exclude products where discontinued = true unless specifically analyzing discontinued items

**Stock valuation**: quantity_on_hand * unit_cost for each product

## Example Query

-- Find products below reorder point across all warehouses
SELECT
    p.product_id,
    p.product_name,
    p.reorder_point,
    SUM(i.quantity_on_hand) as total_stock,
    p.unit_cost,
    (p.reorder_point - SUM(i.quantity_on_hand)) as units_to_reorder
FROM products p
JOIN inventory i ON p.product_id = i.product_id
WHERE p.discontinued = false
GROUP BY p.product_id, p.product_name, p.reorder_point, p.unit_cost
HAVING SUM(i.quantity_on_hand) <= p.reorder_point
ORDER BY units_to_reorder DESC;
""",
    },
]


system_prompt = """
You are a SQL query assistant that helps users.
Write queries against business databases.
"""


@tool
def load_skill(skill_name: str, runtime: ToolRuntime) -> Command:
    for skill in SKILLS:
        if skill["name"] == skill_name:
            skill_content = f"Loaded skill: {skill_name}\n\n{skill['content']}"

            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=skill_content,
                            tool_call_id=runtime.tool_call_id,
                        )
                    ],
                    "skills_loaded": [skill_name],
                }
            )

    available = ", ".join(s["name"] for s in SKILLS)
    return Command(
        update={
            "messages": [
                ToolMessage(
                    content=f"Skill '{skill_name}' not found. Available skills: {available}",
                    tool_call_id=runtime.tool_call_id,
                )
            ]
        }
    )


@tool
def write_sql_query(
    query: str,
    skill: str,
    runtime: ToolRuntime,
) -> str:
    skills_loaded = runtime.state.get("skills_loaded", [])

    if skill not in skills_loaded:
        return (
            f"Error: You must load the '{skill}' skill first "
            f"to understand the database schema before writing queries. "
            f"Use load_skill('{skill}') to load the schema."
        )

    return (
        f"SQL Query for {skill}:\n\n"
        f"```sql\n{query}\n```\n\n"
        f"✓ Query validated against {skill} schema\n"
        f"Ready to execute against the database."
    )


class SkillMiddleware(AgentMiddleware[SkillState]):
    tools = [load_skill, write_sql_query()]

    def __init__(self):
        skills_list = []
        for skill in SKILLS:
            skills_list.append(f"- **{skill['name']}**: {skill['description']}")
        self.skills_prompt = "\n".join(skills_list)

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:

        skills_addendum = (
            f"\n\n## Available Skills\n\n{self.skills_prompt}\n\n"
            "Use the load_skill tool when you need detailed information "
            "about handling a specific type of request."
        )

        new_content = list(request.system_message.content_blocks) + [
            {"type": "text", "text": skills_addendum}
        ]
        new_system_message = SystemMessage(content=new_content)
        modified_request = request.override(system_message=new_system_message)
        return handler(modified_request)


agent = create_agent(
    model,
    system_prompt=system_prompt,
    middleware=[
        SkillMiddleware(),
        # HumanInTheLoopMiddleware(
        #     interrupt_on={"sql_db_query": True},  # I can remove the edit option later
        #     description_prefix="DB Query Tool is pending approval",
        # ),
    ],
    checkpointer=InMemorySaver(),
)

question = """Write a SQL query to find all customers?.
who made orders over $1000 in the last month
"""
config = {"configurable": {"thread_id": "1"}}


# Ask for a SQL query
result = agent.invoke(
    {"messages": [{"role": "user", "content": question}]},
    config,
)

# Print the conversation
for message in result["messages"]:
    if hasattr(message, "pretty_print"):
        message.pretty_print()
    else:
        print(f"{message.type}: {message.content}")

# for step in agent.stream(
#     {"messages": [{"role": "user", "content": question}]},
#     config,
#     stream_mode="values",
# ):
#     if "__interrupt__" in step:
#         print("INTERRUPTED:")
#         interrupt = step["__interrupt__"][0]
#         for request in interrupt.value["action_requests"]:
#             print(request["description"])
#     elif "messages" in step:
#         step["messages"][-1].pretty_print()
#     else:
#         pass
#
# for step in agent.stream(
#     Command(resume={"decisions": [{"type": "approve"}]}),
#     config,
#     stream_mode="values",
# ):
#     if "__interrupt__" in step:
#         print("INTERRUPTED:")
#         interrupt = step["__interrupt__"][0]
#         for request in interrupt.value["action_requests"]:
#             print(request["description"])
#     elif "messages" in step:
#         step["messages"][-1].pretty_print()
#     else:
#         pass
