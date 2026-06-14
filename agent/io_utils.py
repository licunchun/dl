from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> Path:
    ensure_dir(path.parent)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp_path.replace(path)
    return path


def append_jsonl(path: Path, data: dict[str, Any]) -> Path:
    ensure_dir(path.parent)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False, sort_keys=True) + "\n")
        f.flush()
        try:
            import os

            os.fsync(f.fileno())
        except OSError:
            pass
    return path


def read_jsonl_records(path: Path, quarantine_path: Path | None = None) -> dict[str, Any]:
    if not path.exists():
        return {"records": [], "errors": []}
    records: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
            if isinstance(item, dict):
                records.append(item)
            else:
                errors.append({"path": str(path), "line_no": line_no, "error": "non_object_json", "raw": line[:300]})
        except json.JSONDecodeError as exc:
            errors.append({"path": str(path), "line_no": line_no, "error": str(exc), "raw": line[:300]})
    if quarantine_path and errors:
        ensure_dir(quarantine_path.parent)
        with quarantine_path.open("a", encoding="utf-8") as f:
            for error in errors:
                f.write(json.dumps(error, ensure_ascii=False, sort_keys=True) + "\n")
            f.flush()
            try:
                import os

                os.fsync(f.fileno())
            except OSError:
                pass
    return {"records": records, "errors": errors}
