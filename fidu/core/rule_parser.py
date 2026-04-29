import yaml


def load_yaml(file_path: str) -> dict:
    with open(file_path, encoding="utf-8") as file:
        return yaml.safe_load(file)
