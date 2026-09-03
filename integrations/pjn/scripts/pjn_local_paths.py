"""Per-user local paths for PJN browser and token state.

Authentication state must never live inside Dropbox or a Git working tree.
Set PJN_LOCAL_STATE_DIR only when an administrator needs an alternate local
location.
"""

from __future__ import annotations

import os
from pathlib import Path


def local_state_dir() -> Path:
    override = os.environ.get("PJN_LOCAL_STATE_DIR")
    if override:
        return Path(override).expanduser()
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return base / "SegundoCerebroJuridico" / "PJN"


def token_cache_file() -> Path:
    return local_state_dir() / "pjn-token-cache.json"


def browser_profile_dir() -> Path:
    return local_state_dir() / "browser-profile"


def node_tools_dir() -> Path:
    return local_state_dir() / "node-tools"


def runs_dir() -> Path:
    return local_state_dir() / "runs"


def logs_dir() -> Path:
    return local_state_dir() / "logs"
