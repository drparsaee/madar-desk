"""Explicit, side-effect-free legacy sample seed for synthetic contract tests.

Never changes real first-run behavior. The caller must already have patched
native_app.datadir to an isolated TemporaryDirectory.
"""
from pathlib import Path
import tempfile

import native_app
from offline_exchange import atomic_json


def seed_legacy_example_state(bridge):
    """Return a new Bridge opened against a pre-populated synthetic JSON state.

    Using Bridge.saveState for this setup would publish lifecycle/automation
    receipts, invalidating tests that expect zero activity before their action.
    """
    temp = Path(tempfile.gettempdir()).resolve()
    path = bridge.path.resolve()
    if not path.is_relative_to(temp):
        raise AssertionError("Refusing to seed a non-temporary Madar profile")
    if bridge._unified_store is not None:
        raise AssertionError("Sample fixture must be seeded before SQLite activation")
    atomic_json(bridge.path, native_app.normalize_state(native_app.initial_state()))
    return native_app.Bridge()
