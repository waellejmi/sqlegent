DEFAULT_QUESTIONS = {
    "success": "Which genre on average has the longest tracks?",
    "empty_result": "give me the names of all employees born after 1990-01-01",
    "skipped": "What is the airspeed velocity of an unladen swallow?",
    "complex1": "Which 5 artists generated the most revenue, and what is their total revenue and number of tracks sold?",
    "complex2": "Which customers spent more than the average customer spending, and what is their total amount spent?",
    "instruction_test": "List top 4 most bought tracks of all time.",
    "northwind1": "For each category, display the number of its products that aren't discontinued (they are continued or there is a NULL in the discontinued column). Show the columns named category_name and products_number. Show only the rows for which the number of such products is greater than 1. Also, don't show the row for the Other category.",
    "northwind2": """
                All wines in the product table have a name starting with Wine. Find the:

                Number of such products in the table (products_number).
                Total number of units in stock (units_number).
                Average product price (average_price).
                Ratio of the maximum price to the minimum price (max_to_min_ratio).
                Difference between the maximum price and the average price (max_to_average).
                Difference between the average and minimum price (average_to_min).

                Round the four last columns to two decimal points.
                """,
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
DEFAULT_QUESTION_KEY = "success"
