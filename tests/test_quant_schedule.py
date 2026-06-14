from __future__ import annotations

from pathlib import Path

from agent.config import RunConfig
from agent import schedule


def test_schedule_writes_cron_example(tmp_path: Path, monkeypatch) -> None:
    cfg = RunConfig(
        run_date="20260604",
        data_root=tmp_path / "data",
        output_root=tmp_path / "reports",
        knowledge_root=tmp_path / "knowledge_base",
        factor_library=tmp_path / "factor_library",
        offline=True,
    )
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "run_daily.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    monkeypatch.setenv("QUANT_REPO_ROOT", str(repo))

    payload = schedule.run(cfg)
    cron_text = (cfg.run_dir / "cron_example.txt").read_text(encoding="utf-8")

    assert "run_daily.sh" in payload["cron_line"]
    assert payload["cadence"] == "daily"
    assert payload["shell_entrypoint"] is True
    assert payload["uses_run_daily_sh"] is True
    assert payload["install_required"] is True
    assert payload["installed_automatically"] is False
    assert payload["day_of_month"] == "*"
    assert payload["month"] == "*"
    assert payload["day_of_week"] == "*"
    assert "bash" in payload["command"]
    assert payload["script_path"].endswith("run_daily.sh")
    assert payload["script_exists"] is True
    assert payload["log_path"].endswith("daily_cron.log")
    assert payload["log_parent_exists"] is True
    assert payload["log_parent_writable"] is True
    assert payload["cron_line"].startswith("30 18 * * * ")
    assert str(repo / "reports" / "daily_cron.log") in payload["cron_line"]
    assert "1-5" not in payload["cron_line"]
    assert "crontab -e" in payload["note"]
    assert "run_daily.sh" in cron_text
    assert "daily cron" in cron_text
