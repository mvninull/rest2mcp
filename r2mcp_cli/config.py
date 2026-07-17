import json
from typing import Optional
from pathlib import Path

CONFIG_DIR = Path.home() / ".r2mcp"
CONFIG_FILE = CONFIG_DIR / "config.json"
DEFAULT_BASE_URL = "http://localhost:8080"


def _ensure_config_dir():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> dict:
    _ensure_config_dir()
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_config(config: dict):
    _ensure_config_dir()
    CONFIG_FILE.write_text(json.dumps(config, indent=2))


def get_token() -> Optional[str]:
    return load_config().get("token")


def set_token(token: str):
    cfg = load_config()
    cfg["token"] = token
    save_config(cfg)


def clear_token():
    cfg = load_config()
    cfg.pop("token", None)
    save_config(cfg)


def get_base_url() -> str:
    return load_config().get("base_url", DEFAULT_BASE_URL)


def set_base_url(url: str):
    cfg = load_config()
    cfg["base_url"] = url.rstrip("/")
    save_config(cfg)
