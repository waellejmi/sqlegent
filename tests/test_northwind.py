from tools.database import db, get_schema_tool

print(db.get_usable_table_names())

print(get_schema_tool.invoke({"table_names": "Products"}))
