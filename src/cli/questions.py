DEFAULT_QUESTIONS = {
    "success": "Which genre on average has the longest tracks?",
    "empty_result": "give me the names of all employees born after 1990-01-01",
    "skipped": "What is the airspeed velocity of an unladen swallow?",
    "complex1": "Which 5 artists generated the most revenue, and what is their total revenue and number of tracks sold?",
    "complex2": "Which customers spent more than the average customer spending, and what is their total amount spent?",
    "instruction_test": "List top 4 most bought tracks of all time.",
    "northwind": "Find the top 3 employees who generated the highest total revenue from orders in 1997, including the employeeÔÇÖs full name, total revenue, and the number of distinct customers they served. Only include orders where the total order amount exceeds $5,000.",
    "hard1": """
For each country, identify the top-performing sales support agent (employee) based on total revenue from customers they support, but only considering customers who have purchased tracks from at least 3 different genres and have at least 2 invoices in different years.

For each selected agent-country pair:

Compute the average revenue per customer (only among qualifying customers).
Find the most frequently purchased artist (by track count, not revenue) among those customers.
Compute the percentage of revenue contributed by the top 5 tracks (by revenue) within that segment.

Return:

Country
Agent full name
Total revenue
Average revenue per customer
Most popular artist name
Top-5-track revenue percentage

Constraints:

Break ties in agent ranking by number of invoices handled, then by earliest hire date.
Exclude any customers who have ever purchased a track priced below the global median track price.
Only include countries where at least 2 agents compete under these constraints.
""",
}
DEFAULT_QUESTION_KEY = "hard1"
