from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        raw = path.read_text(encoding="utf-8")
    except Exception:
        return None
    try:
        payload = json.loads(raw)
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _normalize_config(config: dict[str, Any]) -> bool:
    changed = False

    messages = config.get("messages")
    if isinstance(messages, dict):
        tts = messages.get("tts")
        if isinstance(tts, dict) and "providers" in tts:
            tts.pop("providers", None)
            changed = True

    channels = config.get("channels")
    if isinstance(channels, dict):
        telegram = channels.get("telegram")
        if isinstance(telegram, dict):
            streaming = telegram.get("streaming")
            valid = {True, False, "off", "partial", "block", "progress"}
            if streaming not in valid:
                telegram["streaming"] = "partial"
                changed = True

    return changed


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def main() -> int:
    state_dir = Path(os.getenv("OPENCLAW_STATE_DIR", "/mnt/openclaw-state")).expanduser()
    config_path = Path(
        os.getenv("OPENCLAW_CONFIG_PATH", str(state_dir / "openclaw.json"))
    ).expanduser()
    readonly_root = Path(os.getenv("OPENCLAW_READONLY_ROOT", "/mnt/openclaw-ro")).expanduser()
    source_path = Path(
        os.getenv("OPENCLAW_BOOTSTRAP_SOURCE_CONFIG", str(readonly_root / "openclaw.json"))
    ).expanduser()

    state_dir.mkdir(parents=True, exist_ok=True)
    _ensure_parent(config_path)

    config = _load_json(config_path)
    if config is None and source_path.exists():
        shutil.copyfile(source_path, config_path)
        config = _load_json(config_path)
        print(f"[bootstrap] copied config from {source_path} -> {config_path}")

    if config is None:
        # Minimal fallback so the CLI has a valid file even if RO config is unavailable.
        config = {"gateway": {"remote": {"url": os.getenv("OPENCLAW_GATEWAY_URL", "")}}}
        config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        print(f"[bootstrap] wrote fallback config at {config_path}")
        return 0

    changed = _normalize_config(config)
    if changed:
        config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        print(f"[bootstrap] normalized incompatible keys in {config_path}")
    else:
        print(f"[bootstrap] config ready at {config_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
