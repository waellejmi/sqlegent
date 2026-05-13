from tools.database import validate_sql

sql_query = """
WITH median_price AS (
    SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY unit_price) AS med
    FROM track
),
customer_stats AS (
    SELECT c.customer_id,
           c.country,
           c.support_rep_id,
           COUNT(DISTINCT t.genre_id) AS genre_cnt,
           COUNT(DISTINCT EXTRACT(YEAR FROM i.invoice_date)) AS year_cnt
    FROM customer c
    JOIN invoice i ON i.customer_id = c.customer_id
    JOIN invoice_line il ON il.invoice_id = i.invoice_id
    JOIN track t ON t.track_id = il.track_id
    GROUP BY c.customer_id, c.country, c.support_rep_id
),
qualifying_customers AS (
    SELECT cs.customer_id,
           cs.country AS customer_country,
           cs.support_rep_id
    FROM customer_stats cs
    CROSS JOIN median_price mp
    WHERE cs.genre_cnt >= 3
      AND cs.year_cnt >= 2
      AND NOT EXISTS (
          SELECT 1
          FROM invoice i2
          JOIN invoice_line il2 ON il2.invoice_id = i2.invoice_id
          JOIN track t2 ON t2.track_id = il2.track_id
          CROSS JOIN median_price mp2
          WHERE i2.customer_id = cs.customer_id
            AND t2.unit_price < mp2.med
      )
),
agent_country_rev AS (
    SELECT e.employee_id,
           e.country,
           e.first_name || ' ' || e.last_name AS agent_name,
           COUNT(DISTINCT i.invoice_id) AS invoice_cnt,
           COUNT(DISTINCT qc.customer_id) AS cust_cnt,
           SUM(il.unit_price * il.quantity) AS total_rev,
           e.hire_date
    FROM qualifying_customers qc
    JOIN employee e ON e.employee_id = qc.support_rep_id
    JOIN invoice i ON i.customer_id = qc.customer_id
    JOIN invoice_line il ON il.invoice_id = i.invoice_id
    GROUP BY e.employee_id, e.country, e.first_name, e.last_name, e.hire_date
),
ranked_agents AS (
    SELECT *,
           RANK() OVER (PARTITION BY country ORDER BY total_rev DESC, invoice_cnt DESC, hire_date ASC) AS rnk,
           COUNT(*) OVER (PARTITION BY country) AS agents_in_country
    FROM agent_country_rev
),
top_agents AS (
    SELECT employee_id, country, agent_name, total_rev, cust_cnt, invoice_cnt, hire_date
    FROM ranked_agents
    WHERE rnk = 1 AND agents_in_country >= 2
),
track_rev AS (
    SELECT ta.employee_id,
           ta.country,
           t.track_id,
           SUM(il.unit_price * il.quantity) AS track_rev
    FROM top_agents ta
    JOIN qualifying_customers qc ON qc.support_rep_id = ta.employee_id
    JOIN invoice i ON i.customer_id = qc.customer_id
    JOIN invoice_line il ON il.invoice_id = i.invoice_id
    JOIN track t ON t.track_id = il.track_id
    GROUP BY ta.employee_id, ta.country, t.track_id
),
track_ranked AS (
    SELECT tr.*, 
           ROW_NUMBER() OVER (PARTITION BY employee_id, country ORDER BY track_rev DESC) AS rev_rank
    FROM track_rev tr
),
top5_pct AS (
    SELECT tr.employee_id,
           tr.country,
           SUM(CASE WHEN tr.rev_rank <= 5 THEN tr.track_rev ELSE 0 END)::numeric / ta.total_rev * 100 AS top5_pct
    FROM track_ranked tr
    JOIN top_agents ta ON ta.employee_id = tr.employee_id AND ta.country = tr.country
    GROUP BY tr.employee_id, tr.country, ta.total_rev
)
SELECT ta.country AS "Country",
       ta.agent_name AS "Agent full name",
       ta.total_rev AS "Total revenue",
       (ta.total_rev / NULLIF(ta.cust_cnt,0)) AS "Average revenue per customer",
       NULL::varchar AS "Most popular artist name",
       tp.top5_pct AS "Top-5-track revenue percentage"
FROM top_agents ta
JOIN top5_pct tp ON tp.employee_id = ta.employee_id AND tp.country = ta.country
ORDER BY ta.total_rev DESC
LIMIT 5;
"""

if not validate_sql(sql_query, dialect=("postgres")):
    print(
        "Failed the static check. Only SELECT and WITH statements are allowed. No multiple statements allowed."
    )
