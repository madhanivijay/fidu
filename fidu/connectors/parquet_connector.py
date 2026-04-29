import pandas as pd

from fidu.connectors.base_connector import BaseConnector


class ParquetConnector(BaseConnector):
    def load_data(self, source_config: dict):
        return pd.read_parquet(source_config["path"])
