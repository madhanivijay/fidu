import os

import pandas as pd

from fidu.connectors.base_connector import BaseConnector


class ADLSFileConnector(BaseConnector):
    def load_data(self, source_config: dict):
        path = source_config["path"]
        file_format = source_config.get("format", "parquet")
        storage_options = {
            "account_name": os.getenv("AZURE_STORAGE_ACCOUNT_NAME"),
            "account_key": os.getenv("AZURE_STORAGE_ACCOUNT_KEY"),
            "tenant_id": os.getenv("AZURE_TENANT_ID"),
            "client_id": os.getenv("AZURE_CLIENT_ID"),
            "client_secret": os.getenv("AZURE_CLIENT_SECRET")
        }
        storage_options = {k: v for k, v in storage_options.items() if v is not None}
        if file_format == "csv":
            return pd.read_csv(path, storage_options=storage_options)
        if file_format == "parquet":
            return pd.read_parquet(path, storage_options=storage_options)
        raise ValueError(f"Unsupported ADLS file format: {file_format}")
