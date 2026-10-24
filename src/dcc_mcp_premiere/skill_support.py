"""Shared result handling for Premiere typed skill entry points."""

from __future__ import annotations

from typing import Any, Callable

from adobe.core.errors import AdobePythonError
from adobe.dcc_mcp import adobe_error, adobe_exception, adobe_success

from .operations import PremiereOperationError


def invoke(message: str, callback: Callable[..., dict[str, Any]], **kwargs: Any):
    try:
        payload = callback(**kwargs)
    except PremiereOperationError as error:
        return adobe_error("Premiere request rejected.", str(error))
    except AdobePythonError as error:
        return adobe_exception(error, message="Premiere operation failed.")
    except Exception as error:
        return adobe_exception(
            error,
            message="Premiere operation failed.",
            include_traceback=False,
        )
    return adobe_success(message, **payload)
