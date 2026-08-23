from tools.database import validate_sql


def test_validate_sql_accepts_single_select():
    assert validate_sql("SELECT 1;", dialect="postgres") is True


def test_validate_sql_accepts_single_with():
    sql = """
        WITH data AS (
            SELECT 1 AS id
        )
        SELECT * FROM data;
    """
    assert validate_sql(sql, dialect="postgres") is True


def test_validate_sql_rejects_multiple_statements():
    sql = """
        SELECT 1;
        SELECT 2;
    """
    assert validate_sql(sql, dialect="postgres") is False


def test_validate_sql_rejects_select_followed_by_insert():
    sql = """
        SELECT 1;
        INSERT INTO users VALUES (1);
    """
    assert validate_sql(sql, dialect="postgres") is False


def test_validate_sql_rejects_insert():
    assert validate_sql("INSERT INTO users VALUES (1);", dialect="postgres") is False
