from utils.helpers import (
    _canonicalize_table_names,
    normalize_table_names,
    normalize_table_names_csv,
)

assert normalize_table_names("Products") == ["Products"]
assert normalize_table_names(" Products , Products ") == ["Products"]
assert normalize_table_names("{'Products'}") == ["Products"]
assert normalize_table_names(["['Products']"]) == ["Products"]
assert normalize_table_names_csv(["Products", "Orders"]) == "Orders,Products"

assert _canonicalize_table_names(
    "products",
    ["Categories", "Products", "Orders"],
) == ["Products"]
