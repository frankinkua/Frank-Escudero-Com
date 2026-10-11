import json
import sys
import os

def validate_catalog(path):
    if not os.path.exists(path):
        print(f"Error: {path} not found.")
        sys.exit(1)

    with open(path, 'r') as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON in {path}: {e}")
            sys.exit(1)

    required_keys = ["schema_version", "generated_at", "subject", "search_queries", "items"]
    for key in required_keys:
        if key not in data:
            print(f"Error: Missing required key '{key}' in catalog.")
            sys.exit(1)

    if data.get("schema_version") != 1:
        print("Error: schema_version must be 1.")
        sys.exit(1)

    items = data.get("items", [])
    item_required_keys = ["id", "type", "title", "source_url", "asset_url", "local_path", "person", "tags", "related_tags", "publisher", "date", "retrieved_at", "rights_status", "rights_evidence", "caption", "identity_evidence"]

    for item in items:
        for key in item_required_keys:
            if key not in item:
                print(f"Error: Missing required key '{key}' in item with id '{item.get('id', 'UNKNOWN')}'.")
                sys.exit(1)

    print("Catalog validation passed!")

if __name__ == "__main__":
    validate_catalog("inbox/media/jules-frank/catalog.json")
