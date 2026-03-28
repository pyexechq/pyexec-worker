"""
config.py — Configuration loader for the pyexec-worker agent.

Priority (highest → lowest):
  1. Environment variables  (PYEXEC_SERVER_URL, PYEXEC_AGENT_TOKEN, …)
  2. Config file            (~/.pyexec-worker/config.json)
  3. Hard-coded defaults
"""

import json
import os
from pathlib import Path

_CONFIG_DIR = Path.home() / '.pyexec-worker'
_CONFIG_FILE = _CONFIG_DIR / 'config.json'
_PRIVATE_KEY_FILE = _CONFIG_DIR / 'private.pem'
_PUBLIC_KEY_FILE = _CONFIG_DIR / 'public.pem'
_AGENT_TOKEN_FILE = _CONFIG_DIR / 'agent.token'


def _load_file_config() -> dict:
    if _CONFIG_FILE.exists():
        try:
            return json.loads(_CONFIG_FILE.read_text())
        except Exception:
            return {}
    return {}


def _cfg(key: str, env_var: str, file_cfg: dict, default=None):
    """Return value from env → file → default."""
    return os.environ.get(env_var) or file_cfg.get(key) or default


def load() -> dict:
    """Return the resolved configuration dict."""
    file_cfg = _load_file_config()

    # Agent token from dedicated file (preferred) or config / env
    token_from_file = None
    if _AGENT_TOKEN_FILE.exists():
        token_from_file = _AGENT_TOKEN_FILE.read_text().strip()

    return {
        'server_url': _cfg('server_url', 'PYEXEC_SERVER_URL', file_cfg, 'http://localhost:8000'),
        'agent_token': os.environ.get('PYEXEC_AGENT_TOKEN') or token_from_file or file_cfg.get('agent_token'),
        'agent_name': _cfg('agent_name', 'PYEXEC_AGENT_NAME', file_cfg, 'Local Worker'),
        'poll_interval': int(_cfg('poll_interval', 'PYEXEC_POLL_INTERVAL', file_cfg, 5)),
        'heartbeat_interval': int(_cfg('heartbeat_interval', 'PYEXEC_HEARTBEAT_INTERVAL', file_cfg, 30)),
        'max_concurrent_steps': int(_cfg('max_concurrent_steps', 'PYEXEC_MAX_CONCURRENT', file_cfg, 4)),
        'docker_image': _cfg('docker_image', 'PYEXEC_DOCKER_IMAGE', file_cfg, 'python:3.11-slim'),
        'private_key_path': str(_PRIVATE_KEY_FILE),
        'public_key_path': str(_PUBLIC_KEY_FILE),
        'use_websocket': _cfg('use_websocket', 'PYEXEC_USE_WEBSOCKET', file_cfg, 'true').lower() == 'true',
    }


def save(updates: dict) -> None:
    """Persist updates to the config file."""
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    existing = _load_file_config()
    existing.update(updates)
    _CONFIG_FILE.write_text(json.dumps(existing, indent=2))


def save_agent_token(raw_token: str) -> None:
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _AGENT_TOKEN_FILE.write_text(raw_token)
    _AGENT_TOKEN_FILE.chmod(0o600)


def config_dir() -> Path:
    return _CONFIG_DIR
