# tenant_context.py
import os
import json
from pathlib import Path

# This variable can be overridden in tests before calling load_tenant_context
TENANTS_FILE = "tenants.json"

def load_tenant_context(guild_id: int, channel_id: int) -> dict | None:
    """
    Dynamically load the tenants JSON, then return either:
     - channel‑specific config if defined, or
     - global guild config if not, or
     - None if the guild isn't in the file.
    """
    if not os.path.exists(TENANTS_FILE):
        raise FileNotFoundError(f"{TENANTS_FILE} not found")

    with open(TENANTS_FILE, "r") as f:
        tenants = json.load(f)

    guild_cfg = tenants.get(str(guild_id))
    if not guild_cfg:
        # no such guild
        return None

    # Check for channel override
    chan_cfg = guild_cfg.get("channels", {}).get(str(channel_id))
    if chan_cfg:
        cfg = {**guild_cfg, **chan_cfg}
    else:
        cfg = guild_cfg

    # Ensure the data and vector dirs exist
    Path(cfg["data_dir"]).mkdir(parents=True, exist_ok=True)
    Path(cfg["vector_store_path"]).mkdir(parents=True, exist_ok=True)

    return cfg
