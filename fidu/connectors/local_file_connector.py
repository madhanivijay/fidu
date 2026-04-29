import pandas as pd

from fidu.connectors.base_connector import BaseConnector


class LocalFileConnector(BaseConnector):
    def load_data(self, source_config: dict):
        path = source_config["path"]
        file_format = source_config.get("format", "csv")
        if file_format == "csv":
            return pd.read_csv(path)
        if file_format == "parquet":
            return pd.read_parquet(path)
        raise ValueError(f"Unsupported local file format: {file_format}")
