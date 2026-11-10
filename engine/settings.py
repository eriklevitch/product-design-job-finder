"""Shared helpers: where files live, reading settings and keys.

Everything is resolved from the project folder, so the scripts work no
matter which folder you run them from (or when double-clicked).
"""
import os
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yaml"
ENV_PATH = ROOT / ".env"


def load_env(path: Path = ENV_PATH) -> None:
    """Reads KEY=value lines from .env into the environment. Values that
    are already set (for example in your shell profile) win, so older
    setups that export keys in ~/.zshrc keep working."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().removeprefix("export ").strip()
        value = value.strip().strip('"').strip("'")
        if key and value and not os.environ.get(key):
            os.environ[key] = value


def save_env(updates: dict, path: Path = ENV_PATH) -> None:
    """Adds or replaces KEY=value lines in .env, keeping everything else."""
    lines = path.read_text().splitlines() if path.exists() else []
    remaining = dict(updates)
    out = []
    for line in lines:
        key = line.split("=", 1)[0].strip().removeprefix("export ").strip()
        if key in remaining:
            out.append(f"{key}={remaining.pop(key)}")
        else:
            out.append(line)
    out += [f"{k}={v}" for k, v in remaining.items()]
    path.write_text("\n".join(out) + "\n")
    try:
        path.chmod(0o600)  # keys: readable by you only
    except OSError:
        pass
    for k, v in updates.items():
        os.environ[k] = v


def env(name: str | None) -> str | None:
    """An environment value, or None if it's missing or blank."""
    if not name:
        return None
    value = os.environ.get(name, "").strip()
    return value or None


def load_config() -> dict:
    """Reads config.yaml, or explains how to create it."""
    if not CONFIG_PATH.exists():
        print("No settings found yet.")
        print("Double-click 'Set Up.command' in the job-search folder to create them.")
        sys.exit(1)
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f) or {}
    return config


def resolve_path(p: str) -> Path:
    """Relative paths in config.yaml are relative to the project folder."""
    path = Path(p).expanduser()
    return path if path.is_absolute() else ROOT / path
