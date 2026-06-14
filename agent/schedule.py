from __future__ import annotations

import os
from pathlib import Path
import shlex
from typing import Any

from .config import RunConfig, load_config
from .io_utils import write_json


def cron_line(repo_root: Path, hour: int = 18, minute: int = 30) -> str:
    script = repo_root / "run_daily.sh"
    log_path = repo_root / "reports" / "daily_cron.log"
    return (
        f"{minute} {hour} * * * cd {shlex.quote(str(repo_root))} && "
        f"bash {shlex.quote(str(script))} >> {shlex.quote(str(log_path))} 2>&1"
    )


def run(config: RunConfig | None = None) -> dict[str, Any]:
    cfg = config or load_config()
    repo_root = Path(os.environ.get("QUANT_REPO_ROOT", Path.cwd())).resolve()
    script_path = repo_root / "run_daily.sh"
    log_path = repo_root / "reports" / "daily_cron.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    line = cron_line(repo_root)
    install_path = cfg.run_dir / "cron_example.txt"
    install_path.parent.mkdir(parents=True, exist_ok=True)
    install_path.write_text(
        "# Example daily cron entry. Review before installing with crontab -e.\n"
        f"{line}\n",
        encoding="utf-8",
    )
    payload = {
        "agent": "schedule",
        "run_date": cfg.run_date,
        "cadence": "daily",
        "shell_entrypoint": True,
        "uses_run_daily_sh": True,
        "installed_automatically": False,
        "install_required": True,
        "minute": 30,
        "hour": 18,
        "day_of_month": "*",
        "month": "*",
        "day_of_week": "*",
        "repo_root": str(repo_root),
        "command": (
            f"cd {shlex.quote(str(repo_root))} && "
            f"bash {shlex.quote(str(script_path))} >> {shlex.quote(str(log_path))} 2>&1"
        ),
        "script_path": str(script_path),
        "script_exists": script_path.exists(),
        "log_path": str(log_path),
        "log_parent": str(log_path.parent),
        "log_parent_exists": log_path.parent.exists(),
        "log_parent_writable": os.access(log_path.parent, os.W_OK),
        "cron_line": line,
        "cron_example_path": str(install_path),
        "note": "Not installed automatically; use crontab -e after reviewing paths and environment.",
    }
    write_json(cfg.run_dir / "schedule.json", payload)
    return payload


if __name__ == "__main__":
    run()
