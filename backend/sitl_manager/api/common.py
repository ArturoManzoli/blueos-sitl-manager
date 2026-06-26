import asyncio
from functools import wraps
from typing import Any, Callable

from fastapi import HTTPException, status
from loguru import logger


def to_http_exception(endpoint: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap a route so unexpected errors become 500s instead of leaking tracebacks."""
    is_async = asyncio.iscoroutinefunction(endpoint)

    @wraps(endpoint)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            if is_async:
                return await endpoint(*args, **kwargs)
            return endpoint(*args, **kwargs)
        except HTTPException:
            raise
        except Exception as error:
            logger.exception(f"{endpoint.__name__} failed")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(error)) from error

    return wrapper
