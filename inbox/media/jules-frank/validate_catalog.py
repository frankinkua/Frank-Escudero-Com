import json
import sys
import os
import urllib.parse

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

    ids = set()
    errors = 0
    for item in items:
        for key in item_required_keys:
            if key not in item:
                print(f"Error: Missing required key '{key}' in item with id '{item.get('id', 'UNKNOWN')}'.")
                errors += 1

        item_id = item.get('id')
        if item_id in ids:
            print(f"Error: Duplicate ID found: {item_id}")
            errors += 1
        ids.add(item_id)

        # Check URL validity (if present)
        source_url = item.get('source_url')
        if source_url:
            parsed = urllib.parse.urlparse(source_url)
            if not all([parsed.scheme, parsed.netloc]):
                print(f"Error: Invalid source_url '{source_url}' in item '{item_id}'")
                errors += 1
        else:
             print(f"Error: source_url is required for item '{item_id}' unless evidence_type is owner_report (not applicable to items in catalog.json).")
             errors += 1

        # Check rights
        if not item.get('rights_status') or not item.get('rights_evidence'):
            print(f"Error: rights_status and rights_evidence must be populated for item '{item_id}'.")
            errors += 1

    # Validate metrics.json
    metrics_path = os.path.join(os.path.dirname(path), 'metrics.json')
    if os.path.exists(metrics_path):
        with open(metrics_path, 'r') as f:
            metrics_data = json.load(f)
            for m in metrics_data.get('metrics', []):
                if m.get('evidence_type') == 'owner_report':
                    if m.get('source_url') is not None:
                        print(f"Error: Metric '{m.get('id')}' is an owner report but has a source_url.")
                        errors += 1
    else:
        print("Warning: metrics.json not found.")

    if errors > 0:
        print(f"Validation failed with {errors} errors.")
        sys.exit(1)

    print("Catalog validation passed!")

if __name__ == "__main__":
    validate_catalog("inbox/media/jules-frank/catalog.json")
