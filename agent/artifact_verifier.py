from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import RunConfig, load_config
from .io_utils import read_json, write_json


MUTABLE_READINESS_PATHS = {"READINESS_REPORT.json", "READINESS_REPORT.md"}
VERIFICATION_OUTPUT_NAMES = {"artifact_verification.json"}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _resolve_manifest_path(cfg: RunConfig, record: dict[str, Any]) -> Path:
    raw_path = record.get("path")
    if raw_path:
        return Path(raw_path)
    rel = str(record.get("relative_path") or "")
    rel_path = Path(rel)
    if rel_path.is_absolute():
        return rel_path
    run_candidate = cfg.run_dir / rel_path
    if run_candidate.exists():
        return run_candidate
    return cfg.output_root / rel_path


def verify_manifest(
    config: RunConfig | None = None,
    *,
    skip_mutable_readiness: bool = True,
    write_output: bool = True,
) -> dict[str, Any]:
    cfg = config or load_config()
    manifest_path = cfg.run_dir / "artifact_manifest.json"
    manifest = read_json(manifest_path, {})
    files = manifest.get("files") or []
    checked_files: list[dict[str, Any]] = []
    skipped_files: list[dict[str, Any]] = []
    missing_files: list[dict[str, Any]] = []
    hash_mismatches: list[dict[str, Any]] = []
    missing_hashes: list[dict[str, Any]] = []

    for record in files:
        rel = str(record.get("relative_path") or record.get("path") or "")
        name = Path(rel).name
        if name in VERIFICATION_OUTPUT_NAMES:
            skipped_files.append({"relative_path": rel, "reason": "verification_output"})
            continue
        if skip_mutable_readiness and rel in MUTABLE_READINESS_PATHS:
            skipped_files.append({"relative_path": rel, "reason": "mutable_readiness_output"})
            continue
        expected = record.get("sha256")
        if not expected:
            missing_hashes.append({"relative_path": rel})
            continue
        path = _resolve_manifest_path(cfg, record)
        if not path.exists():
            missing_files.append({"relative_path": rel, "path": str(path)})
            continue
        actual = _sha256(path)
        checked_files.append({"relative_path": rel, "path": str(path), "sha256": actual})
        if actual != expected:
            hash_mismatches.append({
                "relative_path": rel,
                "path": str(path),
                "expected_sha256": expected,
                "actual_sha256": actual,
            })

    manifest_present = bool(files)
    status = "pass" if (
        manifest_present
        and checked_files
        and not missing_files
        and not hash_mismatches
        and not missing_hashes
    ) else "fail"
    payload = {
        "agent": "artifact_verifier",
        "run_date": cfg.run_date,
        "status": status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "manifest_path": str(manifest_path),
        "manifest_generated_at": manifest.get("generated_at"),
        "manifest_file_count": len(files),
        "checked_file_count": len(checked_files),
        "skipped_file_count": len(skipped_files),
        "missing_file_count": len(missing_files),
        "hash_mismatch_count": len(hash_mismatches),
        "missing_hash_count": len(missing_hashes),
        "skip_mutable_readiness": skip_mutable_readiness,
        "checked_files": checked_files,
        "skipped_files": skipped_files,
        "missing_files": missing_files,
        "hash_mismatches": hash_mismatches,
        "missing_hashes": missing_hashes,
    }
    if write_output:
        write_json(cfg.run_dir / "artifact_verification.json", payload)
        write_json(cfg.output_root / "artifact_verification_latest.json", payload)
    return payload


def run(config: RunConfig | None = None) -> dict[str, Any]:
    return verify_manifest(config)


if __name__ == "__main__":
    run()
