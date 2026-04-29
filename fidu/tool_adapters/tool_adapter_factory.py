"""Tool-adapter registry + lookup."""

from fidu.core.registry import PluginRegistry

tool_adapter_registry: PluginRegistry = PluginRegistry("DQ tool")


def _soda():
    from fidu.tool_adapters.soda_adapter import SodaToolAdapter
    return SodaToolAdapter()


def _gx():
    from fidu.tool_adapters.gx_adapter import GreatExpectationsToolAdapter
    return GreatExpectationsToolAdapter()


def _deequ():
    from fidu.tool_adapters.deequ_adapter import DeequToolAdapter
    return DeequToolAdapter()


tool_adapter_registry.register("soda", _soda)
tool_adapter_registry.register("great_expectations", _gx, aliases=["gx"])
tool_adapter_registry.register("deequ", _deequ, aliases=["pydeequ"])


def get_tool_adapter(tool_name: str):
    return tool_adapter_registry.create(tool_name)


def register_tool_adapter(name, factory, aliases=None):
    """Public hook for downstream code to register a custom tool adapter."""
    tool_adapter_registry.register(name, factory, aliases=aliases)
