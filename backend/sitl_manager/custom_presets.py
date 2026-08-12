"""Persistence for the presets a user saves, imports or edits, vehicle and location alike.

A saved preset whose name matches a built-in is an override: it shadows the curated
definition for as long as it exists, and deleting it brings the built-in back. That is what
lets a built-in be edited without it ever being possible to lose one.
"""

import json
import re
from pathlib import Path
from typing import Generic, List, Optional, Sequence, Type, TypeVar

from loguru import logger

from sitl_manager.models import LocationPreset, NamedPreset, VehiclePreset
from sitl_manager.settings import CUSTOM_LOCATIONS_DIR, CUSTOM_PRESETS_DIR

# How many presets one row of buttons holds before they stop fitting, built-ins included.
# Names are ellipsized well before this, so the limit is about the row's own width rather
# than any storage concern.
MAX_PRESETS = 9

PresetT = TypeVar("PresetT", bound=NamedPreset)


class PresetConflictError(RuntimeError):
    """A request the stored presets cannot take: no room left, or a built-in that must stay."""


class UnknownPresetError(RuntimeError):
    """A preset was asked for by a name nothing answers to, built-in or stored."""


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "preset"


class PresetStore(Generic[PresetT]):
    """A directory of presets stored one JSON file per preset, named after its slug."""

    def __init__(self, directory: Path, model: Type[PresetT]) -> None:
        self.directory = directory
        self.model = model

    def _path(self, name: str) -> Path:
        return self.directory / f"{_slug(name)}.json"

    def list(self) -> List[PresetT]:
        """Every stored preset, skipping any file that fails to parse."""
        presets: List[PresetT] = []
        if not self.directory.is_dir():
            return presets
        for path in sorted(self.directory.glob("*.json")):
            try:
                presets.append(self.model(**json.loads(path.read_text())))
            except Exception as error:  # noqa: BLE001 - one bad file must not break the list
                logger.warning(f"Ignoring invalid preset {path.name}: {error}")
        return presets

    def get(self, name: str) -> Optional[PresetT]:
        path = self._path(name)
        if not path.is_file():
            return None
        try:
            return self.model(**json.loads(path.read_text()))
        except Exception as error:  # noqa: BLE001 - treat an unreadable file as absent
            logger.warning(f"Ignoring invalid preset {path.name}: {error}")
            return None

    def has(self, name: str) -> bool:
        return self._path(name).is_file()

    def save(self, preset: PresetT) -> Path:
        """Write a preset, replacing any stored under the same name."""
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self._path(preset.name)
        # builtin/overridden describe where a preset was found, not what it is, so they are
        # left out of the file: a stored preset that names a built-in is an override by virtue
        # of being there, and re-reading a flag would only let the two disagree.
        path.write_text(json.dumps(preset.dict(exclude={"builtin", "overridden"}), indent=2))
        return path

    def delete(self, name: str) -> bool:
        """Remove a stored preset, returning whether there was a file to remove."""
        path = self._path(name)
        if path.is_file():
            path.unlink()
            return True
        return False


VEHICLE_STORE: PresetStore[VehiclePreset] = PresetStore(CUSTOM_PRESETS_DIR, VehiclePreset)
LOCATION_STORE: PresetStore[LocationPreset] = PresetStore(CUSTOM_LOCATIONS_DIR, LocationPreset)


def ensure_room(store: PresetStore[PresetT], builtin_names: Sequence[str], name: str) -> None:
    """Refuse a preset that would push the row past ``MAX_PRESETS``.

    Overwriting something that is already listed, built-in or saved, always fits: it takes a
    slot that is spoken for either way.
    """
    if name in builtin_names or store.has(name):
        return
    saved = [preset for preset in store.list() if preset.name not in builtin_names]
    if len(builtin_names) + len(saved) >= MAX_PRESETS:
        raise PresetConflictError(
            f"There is room for {MAX_PRESETS} presets and they are all taken. " "Delete one before adding another."
        )


def rename(store: PresetStore[PresetT], listed: Sequence[PresetT], name: str, new_name: str) -> PresetT:
    """Store the preset called ``name`` under ``new_name`` and return it.

    A saved preset moves. A built-in is copied instead, because it cannot be removed, so
    renaming one leaves it — and any edit made to it — exactly where it was. The new name has
    to be free either way, so a rename can never quietly take another preset's place.
    """
    source = next((preset for preset in listed if preset.name == name), None)
    if source is None:
        raise UnknownPresetError(f"Unknown preset '{name}'.")
    if new_name == name:
        return source
    if any(preset.name == new_name for preset in listed):
        raise PresetConflictError(f"A preset named '{new_name}' already exists.")

    builtin_names = [preset.name for preset in listed if preset.builtin]
    moving = name not in builtin_names
    if not moving:
        ensure_room(store, builtin_names, new_name)

    renamed = source.copy(update={"name": new_name, "builtin": None, "overridden": None})
    store.save(renamed)
    if moving:
        store.delete(name)
    return renamed


def remove(store: PresetStore[PresetT], builtin_names: Sequence[str], name: str) -> str:
    """Delete a saved preset, or revert an edited built-in, describing what happened.

    A built-in is only ever reverted: what gets deleted is the saved preset shadowing it, and
    the curated definition takes its place again in the row.
    """
    if name in builtin_names:
        if not store.delete(name):
            raise PresetConflictError(f"'{name}' is a built-in preset and cannot be deleted.")
        return f"Reverted '{name}' to its built-in definition."
    if not store.delete(name):
        raise UnknownPresetError(f"Unknown preset '{name}'.")
    return f"Deleted preset '{name}'."
