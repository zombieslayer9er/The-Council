"""Optional read-only HTTP/streaming boundary."""

from typing import Any


def create_app(*args: Any, **kwargs: Any) -> Any:
    from botnet_council.api.app import create_app as factory

    return factory(*args, **kwargs)


__all__ = ["create_app"]
