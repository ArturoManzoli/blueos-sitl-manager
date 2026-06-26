import json
import re
from pathlib import Path
from typing import List

from loguru import logger

from sitl_manager.models import VehiclePreset
from sitl_manager.settings import CUSTOM_PRESETS_DIR


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "preset"


def _ensure_dir() -> Path:
    CUSTOM_PRESETS_DIR.mkdir(parents=True, exist_ok=True)
    return CUSTOM_PRESETS_DIR


def list_custom_presets() -> List[VehiclePreset]:
    """Load every persisted custom preset, skipping any file that fails to parse."""
    presets: List[VehiclePreset] = []
    if not CUSTOM_PRESETS_DIR.is_dir():
        return presets
    for path in sorted(CUSTOM_PRESETS_DIR.glob("*.json")):
        try:
            presets.append(VehiclePreset(**json.loads(path.read_text())))
        except Exception as error:  # noqa: BLE001 - one bad file must not break the list
            logger.warning(f"Ignoring invalid custom preset {path.name}: {error}")
    return presets


def save_custom_preset(preset: VehiclePreset) -> Path:
    """Persist a custom preset as JSON, returning the file path it was written to."""
    path = _ensure_dir() / f"{_slug(preset.name)}.json"
    path.write_text(json.dumps(preset.dict(), indent=2))
    return path
