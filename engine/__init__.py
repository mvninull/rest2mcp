def __getattr__(name):
    if name == "Orchestrator":
        from .orchestrator import Orchestrator

        return Orchestrator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["Orchestrator"]