#! /usr/bin/env python3
import logging
from typing import Any, Dict

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi_versioning import VersionedFastAPI
from loguru import logger
from uvicorn import Config, Server

from sitl_manager import __version__
from sitl_manager.api.v1.routers.environment import environment_router
from sitl_manager.api.v1.routers.location import location_router
from sitl_manager.api.v1.routers.vehicle import vehicle_router
from sitl_manager.http import close_session
from sitl_manager.settings import PORT, SERVICE_NAME, STATIC_DIR

logging.basicConfig(level=logging.INFO)
logger.info("Starting SITL Manager")

fast_api_app = FastAPI(
    title="SITL Manager API",
    description="Configure vehicle type, ambient conditions and location of a BlueOS SITL vehicle.",
)
fast_api_app.include_router(environment_router)
fast_api_app.include_router(location_router)
fast_api_app.include_router(vehicle_router)

app = VersionedFastAPI(fast_api_app, version="1.0.0", prefix_format="/v{major}.{minor}", enable_latest=True)


@app.get("/register_service", include_in_schema=False)
def register_service() -> Dict[str, Any]:
    """Metadata consumed by the BlueOS helper service to add this extension to the sidebar."""
    return {
        "name": "SITL Manager",
        "description": "Manage SITL vehicle type, ambient conditions (wind, waves, current) and spawn location.",
        "icon": "mdi-test-tube",
        "company": "BlueOS Community",
        "version": __version__,
        "new_page": False,
        "webpage": "https://github.com/BlueOS-Community/blueos-sitl-manager",
        "api": "/docs",
        "works_in_relative_paths": True,
    }


@app.on_event("shutdown")
async def _on_shutdown() -> None:
    await close_session()


if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
else:
    logger.warning(f"Static directory {STATIC_DIR} not found; serving API only.")

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse(url="/docs")


def main() -> None:
    config = Config(app=app, host="0.0.0.0", port=PORT, log_config=None)
    Server(config).run()


if __name__ == "__main__":
    main()
