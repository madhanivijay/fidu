import pandas as pd

from fidu.connectors.base_connector import BaseConnector


class CSVConnector(BaseConnector):
    def load_data(self, source_config: dict):
        return pd.read_csv(source_config["path"])
