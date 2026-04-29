from pyspark.sql import SparkSession

from fidu.connectors.base_connector import BaseConnector


class SparkFileConnector(BaseConnector):
    def __init__(self):
        self.spark = SparkSession.builder.appName("EnterpriseDQKit").getOrCreate()

    def load_data(self, source_config: dict):
        file_format = source_config.get("format", "parquet")
        reader = self.spark.read
        for key, value in source_config.get("options", {}).items():
            reader = reader.option(key, value)
        if file_format == "csv":
            return reader.option("header", "true").option("inferSchema", "true").csv(source_config["path"])
        if file_format == "parquet":
            return reader.parquet(source_config["path"])
        if file_format == "delta":
            return reader.format("delta").load(source_config["path"])
        if file_format == "iceberg":
            return self.spark.table(source_config["table"])
        raise ValueError(f"Unsupported Spark file format: {file_format}")
