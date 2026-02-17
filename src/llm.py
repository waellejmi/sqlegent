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
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_community.utilities import SQLDatabase
from langchain_groq import ChatGroq
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command, interrupt

from utils.env_config import MyConfig

config = MyConfig()
project_root = pathlib.Path(__file__).resolve().parent.parent.parent
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

db = SQLDatabase.from_uri(f"sqlite:///{db_path}")


print(f"Dialect: {db.dialect}")
print(f"Available tables: {db.get_usable_table_names()}")
print(f"Sample output: {db.run('SELECT * FROM Artist LIMIT 5;')}")


toolkit = SQLDatabaseToolkit(db=db, llm=model)

sql_tools = toolkit.get_tools()


class SkillState(AgentState):
    skills_loaded: NotRequired[list[str]]


class Skill(TypedDict):
    name: str
    description: str
    content: str


SKILLS: list[Skill] = [
    {
        "name": "music_catalog_analytics",
        "description": "Database schema and business logic for digital music store analytics including artists, albums, tracks, genres, media types, and playlists.",
        "content": """
# Music Catalog Analytics Schema

## Tables

### Artist
- ArtistId (PRIMARY KEY)
- Name

### Album
- AlbumId (PRIMARY KEY)
- Title
- ArtistId (FOREIGN KEY -> Artist.ArtistId)

### Track
- TrackId (PRIMARY KEY)
- Name
- AlbumId (FOREIGN KEY -> Album.AlbumId)
- MediaTypeId (FOREIGN KEY -> MediaType.MediaTypeId)
- GenreId (FOREIGN KEY -> Genre.GenreId)
- Composer
- Milliseconds
- Bytes
- UnitPrice

### Genre
- GenreId (PRIMARY KEY)
- Name

### MediaType
- MediaTypeId (PRIMARY KEY)
- Name

### Playlist
- PlaylistId (PRIMARY KEY)
- Name

### PlaylistTrack
- PlaylistId (FOREIGN KEY -> Playlist.PlaylistId)
- TrackId (FOREIGN KEY -> Track.TrackId)
- COMPOSITE PRIMARY KEY (PlaylistId, TrackId)

## Business Logic

**Track duration conversion**:  
Milliseconds / 60000.0 = minutes  
Milliseconds / 3600000.0 = hours  

**Album value**: Sum of UnitPrice for all tracks in an album.

**Popular genres**: Count tracks per Genre.

**Artist catalog size**: Count albums per Artist and tracks per Artist.

**Long tracks**: Milliseconds > 300000.

**High-value tracks**: UnitPrice > 0.99.

## Example Queries

-- Top 10 artists by total track count and catalog value
SELECT 
    ar.Name AS artist_name,
    COUNT(DISTINCT al.AlbumId) AS album_count,
    COUNT(t.TrackId) AS track_count,
    SUM(t.UnitPrice) AS catalog_value,
    SUM(t.Milliseconds) / 3600000.0 AS total_hours
FROM Artist ar
JOIN Album al ON ar.ArtistId = al.ArtistId
JOIN Track t ON al.AlbumId = t.AlbumId
GROUP BY ar.ArtistId, ar.Name
ORDER BY track_count DESC
LIMIT 10;

-- Find tracks longer than 5 minutes in a specific genre
SELECT 
    t.Name AS track_name,
    ar.Name AS artist,
    al.Title AS album,
    ROUND(t.Milliseconds / 60000.0, 2) AS duration_minutes,
    t.UnitPrice
FROM Track t
JOIN Album al ON t.AlbumId = al.AlbumId
JOIN Artist ar ON al.ArtistId = ar.ArtistId
JOIN Genre g ON t.GenreId = g.GenreId
WHERE t.Milliseconds > 300000
ORDER BY t.Milliseconds DESC;
""",
    },
    {
        "name": "sales_customer_analytics",
        "description": "Database schema and business logic for sales analysis including customers, invoices, invoice lines, and employees.",
        "content": """
# Sales & Customer Analytics Schema

## Tables

### Customer
- CustomerId (PRIMARY KEY)
- FirstName
- LastName
- Company
- Address
- City
- State
- Country
- PostalCode
- Phone
- Fax
- Email
- SupportRepId (FOREIGN KEY -> Employee.EmployeeId)

### Invoice
- InvoiceId (PRIMARY KEY)
- CustomerId (FOREIGN KEY -> Customer.CustomerId)
- InvoiceDate
- BillingAddress
- BillingCity
- BillingState
- BillingCountry
- BillingPostalCode
- Total

### InvoiceLine
- InvoiceLineId (PRIMARY KEY)
- InvoiceId (FOREIGN KEY -> Invoice.InvoiceId)
- TrackId (FOREIGN KEY -> Track.TrackId)
- UnitPrice
- Quantity

### Employee
- EmployeeId (PRIMARY KEY)
- LastName
- FirstName
- Title
- ReportsTo (FOREIGN KEY -> Employee.EmployeeId)
- BirthDate
- HireDate
- Address
- City
- State
- Country
- PostalCode
- Phone
- Fax
- Email

## Business Logic

**Customer lifetime value (CLV)**: SUM(Invoice.Total) grouped by CustomerId.

**Average order value (AOV)**: AVG(Invoice.Total).

**Sales by period**: Group by year or month using strftime on InvoiceDate.

**Support rep performance**: Sum of Invoice totals for customers assigned to each Employee.

**Geographic sales**: Group by BillingCountry or BillingState.

**Repeat customers**: Customers with COUNT(InvoiceId) >= 2.

## Example Queries

-- Monthly sales trend
SELECT 
    strftime('%Y', InvoiceDate) AS year,
    strftime('%m', InvoiceDate) AS month,
    COUNT(*) AS invoice_count,
    ROUND(SUM(Total), 2) AS revenue,
    COUNT(DISTINCT CustomerId) AS unique_customers
FROM Invoice
GROUP BY year, month
ORDER BY year, month;

-- Support rep performance ranking
SELECT 
    e.FirstName || ' ' || e.LastName AS support_rep,
    e.Title,
    COUNT(DISTINCT c.CustomerId) AS assigned_customers,
    COUNT(i.InvoiceId) AS total_orders,
    ROUND(SUM(i.Total), 2) AS total_revenue,
    ROUND(SUM(i.Total) / COUNT(DISTINCT c.CustomerId), 2) AS revenue_per_customer
FROM Employee e
LEFT JOIN Customer c ON e.EmployeeId = c.SupportRepId
LEFT JOIN Invoice i ON c.CustomerId = i.CustomerId
GROUP BY e.EmployeeId, e.FirstName, e.LastName, e.Title
ORDER BY total_revenue DESC;

-- Country sales analysis
SELECT 
    BillingCountry AS country,
    COUNT(DISTINCT CustomerId) AS unique_customers,
    COUNT(*) AS total_orders,
    ROUND(SUM(Total), 2) AS total_revenue,
    ROUND(AVG(Total), 2) AS avg_order_value,
    ROUND(SUM(Total) / COUNT(DISTINCT CustomerId), 2) AS revenue_per_customer
FROM Invoice
GROUP BY BillingCountry
ORDER BY total_revenue DESC;
""",
    },
]


system_prompt = """
You are a SQL query assistant that helps users.
Write queries against business databases.
"""


@tool
def load_skill(skill_name: str, runtime: ToolRuntime) -> Command:
    """Load the full content of a skill into the agent's context.

    Use this when you need detailed information about how to handle a specific
    type of request. This will provide you with comprehensive instructions,
    policies, and guidelines for the skill area.

    Args:
        skill_name: The name of the skill to load
    """
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


class SkillMiddleware(AgentMiddleware[SkillState]):
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
    tools=[load_skill, *sql_tools],
    middleware=[
        SkillMiddleware(),
        # HumanInTheLoopMiddleware(
        #     interrupt_on={"sql_db_query": True},  # I can remove the edit option later
        #     description_prefix="DB Query Tool is pending approval",
        # ),
    ],
    checkpointer=InMemorySaver(),
)

question = """
Write a SQL query to find all customers who made at least one purchase over $20 in 2013.
Then execute the query and return the results.
"""

config = {"configurable": {"thread_id": "1"}}


for step in agent.stream(
    {"messages": [{"role": "user", "content": question}]},
    config,
    stream_mode="values",
):
    if "__interrupt__" in step:
        print("INTERRUPTED:")
        interrupt = step["__interrupt__"][0]
        for request in interrupt.value["action_requests"]:
            print(request["description"])
    elif "messages" in step:
        step["messages"][-1].pretty_print()
    else:
        pass

for step in agent.stream(
    Command(resume={"decisions": [{"type": "approve"}]}),
    config,
    stream_mode="values",
):
    if "__interrupt__" in step:
        print("INTERRUPTED:")
        interrupt = step["__interrupt__"][0]
        for request in interrupt.value["action_requests"]:
            print(request["description"])
    elif "messages" in step:
        step["messages"][-1].pretty_print()
    else:
        pass
