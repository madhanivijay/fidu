import argparse

import yaml

from fidu.core.rule_suggester import suggest_dataset_rules


def parse_columns(columns_text: str):
    cols = []
    for item in columns_text.split(","):
        name, dtype = item.split(":")
        cols.append({"name": name.strip(), "type": dtype.strip()})
    return cols

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--source-type", default="local_file")
    parser.add_argument("--source-format", default="csv")
    parser.add_argument("--path", required=True)
    parser.add_argument("--columns", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    source_config = {"type": args.source_type, "format": args.source_format, "path": args.path}
    rules = suggest_dataset_rules(args.dataset, source_config, parse_columns(args.columns))
    with open(args.output, "w", encoding="utf-8") as file:
        yaml.safe_dump(rules, file, sort_keys=False)
    print(f"Suggested rules written to: {args.output}")

if __name__ == "__main__":
    main()
