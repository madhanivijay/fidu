import os

import pandas as pd

from fidu.connectors.base_connector import BaseConnector


class S3FileConnector(BaseConnector):
    def load_data(self, source_config: dict):
        path = source_config["path"]
        file_format = source_config.get("format", "parquet")
        storage_options = {
            "key": os.getenv("AWS_ACCESS_KEY_ID"),
            "secret": os.getenv("AWS_SECRET_ACCESS_KEY"),
            "token": os.getenv("AWS_SESSION_TOKEN")
        }
        storage_options = {k: v for k, v in storage_options.items() if v is not None}
        if file_format == "csv":
            return pd.read_csv(path, storage_options=storage_options)
        if file_format == "parquet":
            return pd.read_parquet(path, storage_options=storage_options)
        raise ValueError(f"Unsupported S3 file format: {file_format}")
