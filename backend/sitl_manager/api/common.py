import asyncio
from functools import wraps
from typing import Any, Callable

from fastapi import HTTPException, status
from loguru import logger

from sitl_manager import autopilot
from sitl_manager.custom_presets import PresetConflictError, UnknownPresetError


async def require_sitl(refusal: str) -> None:
    """Refuse an operation when the running board is not the simulator.

    Everything this extension writes assumes SITL: applying a preset installs the firmware
    for a whole other vehicle and makes it the default, which on a real board reflashes the
    autopilot wired to the vehicle, and the SIM_* parameters behind the spawn location and
    the ambient conditions exist nowhere else. The frontend hides these actions on a real
    board; this is what makes them impossible rather than merely hidden.
    """
    if not autopilot.is_sitl(await autopilot.get_board()):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"The active board is not SITL; {refusal}.",
        )


def to_http_exception(endpoint: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap a route so unexpected errors become 500s instead of leaking tracebacks.

    The preset store's two refusals are given their real status codes here rather than in
    each route, so the vehicle and location presets answer the same way to the same mistake.
    """
    is_async = asyncio.iscoroutinefunction(endpoint)

    @wraps(endpoint)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            if is_async:
                return await endpoint(*args, **kwargs)
            return endpoint(*args, **kwargs)
        except HTTPException:
            raise
        except PresetConflictError as error:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
        except UnknownPresetError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
        except Exception as error:
            logger.exception(f"{endpoint.__name__} failed")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(error)) from error

    return wrapper
