from sqlglot import exp, parse

sql_query_example = "SELECT g.Name AS Genre, AVG(t.Milliseconds) AS AvgMilliseconds FROM Track t JOIN Genre g ON t.GenreId = g.GenreId GROUP BY g.GenreId, g.Name ORDER BY AvgMilliseconds DESC LIMIT 5"
sub_qeury_example = """
SELECT e.Name, e.Salary
FROM Employees e
WHERE e.Salary > (SELECT AVG(Salary) 
                  FROM Employees 
                  WHERE DepartmentID = e.DepartmentID);
"""
ALLOWED = (
    exp.Select,
    exp.With,
)

FORBIDDEN = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Create,
    exp.Drop,
    exp.Alter,
    exp.Trunc,
)


def validate_sql(query: str) -> bool:
    try:
        statements = parse(query)
    except Exception:
        return False

    if len(statements) != 1:
        return False

    ast = statements[0]

    if not isinstance(ast, ALLOWED):
        return False
    # for id, node in enumerate(ast.walk()):
    #     print(f"Node {id}: {node}")
    #     # if isinstance(node, FORBIDDEN):
    #     return False

    return True


# print(validate_sql(sql_query_example))
print(validate_sql(sub_qeury_example))
