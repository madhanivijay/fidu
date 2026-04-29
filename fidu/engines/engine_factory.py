"""Native execution engine registry."""

from fidu.core.registry import PluginRegistry

engine_registry: PluginRegistry = PluginRegistry("engine")


def _pandas():
    from fidu.engines.pandas_engine import PandasDQEngine
    return PandasDQEngine()


def _sql():
    from fidu.engines.sql_engine import SQLDQEngine
    return SQLDQEngine()


def _spark():
    from fidu.engines.spark_engine import SparkDQEngine
    return SparkDQEngine()


engine_registry.register("pandas", _pandas)
engine_registry.register("sql", _sql)
engine_registry.register("spark", _spark)


def get_engine(engine_name: str):
    return engine_registry.create(engine_name)


def register_engine(name, factory, aliases=None):
    """Public hook for downstream code to register a custom engine."""
    engine_registry.register(name, factory, aliases=aliases)
