import argparse
import sys

import yaml


def load_yaml(path):
    with open(path, encoding="utf-8") as file:
        return yaml.safe_load(file)


def save_yaml(path, data):
    with open(path, "w", encoding="utf-8") as file:
        yaml.safe_dump(data, file, sort_keys=False)


def list_rules(data):
    rules = data.get("rules") or []
    if not rules:
        print("No rules in file.")
        return
    for i, rule in enumerate(rules, start=1):
        print(
            f"{i}. {rule['name']} | type={rule['type']} | "
            f"column={rule.get('column')} | "
            f"status={rule.get('review_status', 'approved')} | "
            f"draft={rule.get('draft', False)}"
        )


def _resolve_index(rules, index):
    if not rules:
        raise SystemExit("Cannot apply --action: rules list is empty.")
    if index is None:
        raise SystemExit("Please provide --index (1-based).")
    if index < 1 or index > len(rules):
        raise SystemExit(
            f"--index {index} is out of range. Valid range: 1..{len(rules)}."
        )
    return rules[index - 1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument(
        "--action",
        required=True,
        choices=["list", "approve", "reject", "approve_all"],
    )
    parser.add_argument("--index", type=int)
    args = parser.parse_args()

    try:
        data = load_yaml(args.file)
    except FileNotFoundError as exc:
        raise SystemExit(f"File not found: {args.file}") from exc
    except yaml.YAMLError as exc:
        raise SystemExit(f"Could not parse YAML in {args.file}: {exc}") from exc

    if not isinstance(data, dict) or "rules" not in data:
        raise SystemExit(f"{args.file} does not contain a 'rules' list.")

    rules = data["rules"] or []

    if args.action == "list":
        list_rules(data)
        return

    if args.action == "approve":
        rule = _resolve_index(rules, args.index)
        rule["draft"] = False
        rule["review_status"] = "approved"
        rule["review_comment"] = "Approved via CLI"
    elif args.action == "reject":
        rule = _resolve_index(rules, args.index)
        rule["draft"] = True
        rule["review_status"] = "rejected"
        rule["review_comment"] = "Rejected via CLI"
    elif args.action == "approve_all":
        for rule in rules:
            rule["draft"] = False
            rule["review_status"] = "approved"
            rule["review_comment"] = "Bulk approved"

    save_yaml(args.file, data)
    print("Updated successfully")


if __name__ == "__main__":
    sys.exit(main())
