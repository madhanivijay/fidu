"""Source connectors. Use ``get_connector(source_type)`` from ``connector_factory``."""

from fidu.connectors.connector_factory import (
    connector_registry,
    get_connector,
    register_connector,
)

__all__ = ["connector_registry", "get_connector", "register_connector"]
