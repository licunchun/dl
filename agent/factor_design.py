from __future__ import annotations

import re
from typing import Any

from .config import RunConfig, load_config
from .io_utils import ensure_dir, read_json, read_jsonl_records, write_json


FACTOR_TEMPLATES = {
    "volume_shock_reversal": [
        {
            "factor_id": "F_VOL_REV_5",
            "name": "放量5日反转",
            "formula": "(1 - rank(ret_5)) * rank(amount_ratio_20)",
            "expression": "shock_reversal_5",
            "horizon_days": 5,
        },
        {
            "factor_id": "F_VWAP_REV_5",
            "name": "VWAP放量反转",
            "formula": "(1 - rank(vwap_dev)) * rank(amount_ratio_20)",
            "expression": "vwap_shock_reversal",
            "horizon_days": 5,
        },
    ],
    "moneyflow_exhaustion": [
        {
            "factor_id": "F_MF_EXHAUST_5",
            "name": "资金流耗尽反转",
            "formula": "(1 - rank(ret_5)) * rank(mf_buy_pressure)",
            "expression": "moneyflow_exhaustion_reversal",
            "horizon_days": 5,
        },
        {
            "factor_id": "F_MF_CONFIRM_5",
            "name": "资金流顺势确认",
            "formula": "rank(ret_5) * rank(mf_buy_pressure)",
            "expression": "moneyflow_confirmed_momentum",
            "horizon_days": 5,
        },
    ],
    "defensive_liquidity_value": [
        {
            "factor_id": "F_VALUE_LIQ_DEF_5",
            "name": "价值流动性防御",
            "formula": "(rank(pb_inv) + rank(liq_inv) + rank(low_vol)) / 3",
            "expression": "value_liquidity_defensive",
            "horizon_days": 5,
        },
    ],
}


def normalize_formula_key(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"[^a-z0-9_+\-*/().]", "", text.lower())


def factor_identity_keys(
    factor_id: str | None,
    formula: str | None,
    formula_key: str | None,
    expression: str | None,
) -> set[str]:
    keys = {
        str(key)
        for key in (factor_id, formula, formula_key, expression)
        if key
    }
    normalized_formula = normalize_formula_key(formula)
    normalized_formula_key = normalize_formula_key(formula_key)
    if normalized_formula:
        keys.add(normalized_formula)
    if normalized_formula_key:
        keys.add(normalized_formula_key)
    return keys


def _failed_factor_keys(cfg: RunConfig) -> tuple[set[str], dict[str, Any]]:
    db = read_json(cfg.knowledge_root / "factor_database" / "factors.json", {"factors": []})
    keys: set[str] = set()
    source_counts = {"factor_database": 0, "failure_memory": 0}
    for factor in db.get("factors", []):
        if factor.get("decision") != "kill":
            continue
        source_counts["factor_database"] += 1
        keys.update(factor_identity_keys(
            factor.get("factor_id"),
            factor.get("formula"),
            factor.get("formula_key"),
            factor.get("expression"),
        ))
    memory_path = cfg.knowledge_root / "failure_memory.jsonl"
    memory_payload = read_jsonl_records(
        memory_path,
        quarantine_path=cfg.knowledge_root / "jsonl_quarantine" / "failure_memory.jsonl.corrupt.jsonl",
    )
    if memory_path.exists():
        for item in memory_payload["records"]:
            source_counts["failure_memory"] += 1
            keys.update(factor_identity_keys(
                item.get("factor_id"),
                item.get("formula"),
                item.get("formula_key"),
                item.get("expression"),
            ))
    audit = {
        "failed_key_count": len(keys),
        "source_counts": source_counts,
        "failure_memory_parse_errors": len(memory_payload["errors"]),
        "failure_memory_quarantine_path": str(cfg.knowledge_root / "jsonl_quarantine" / "failure_memory.jsonl.corrupt.jsonl"),
    }
    return keys, audit


def _provenance(idea: dict[str, Any], research_payload: dict[str, Any], cfg: RunConfig) -> dict[str, Any]:
    return {
        "source_idea_id": idea.get("idea_id"),
        "source_theme": idea.get("theme"),
        "hypothesis": idea.get("hypothesis"),
        "evidence": idea.get("evidence", [])[:5],
        "research_source_quality": research_payload.get("source_quality", {}),
        "created_at_run": cfg.run_date,
    }


def run(config: RunConfig | None = None) -> dict[str, Any]:
    cfg = config or load_config()
    ideas = read_json(cfg.run_dir / "research_ideas.json", {"ideas": []})
    failed, failed_audit = _failed_factor_keys(cfg)
    out_dir = ensure_dir(cfg.run_dir / "candidate_factors")
    library_dir = ensure_dir(cfg.factor_library)
    factors = []
    skipped_factors = []
    for idea in ideas.get("ideas", []):
        for template in FACTOR_TEMPLATES.get(idea.get("theme"), []):
            formula_key = normalize_formula_key(template["formula"])
            matched_keys = [
                key
                for key in factor_identity_keys(
                    template["factor_id"],
                    template["formula"],
                    formula_key,
                    template["expression"],
                )
                if key in failed
            ]
            if matched_keys:
                skipped_factors.append({
                    "factor_id": template["factor_id"],
                    "formula": template["formula"],
                    "formula_key": formula_key,
                    "expression": template["expression"],
                    "source_idea_id": idea.get("idea_id"),
                    "reason": "matched_failed_factor_memory",
                    "matched_keys": matched_keys,
                })
                continue
            factor = dict(template)
            factor["formula_key"] = formula_key
            factor["source_idea_id"] = idea.get("idea_id")
            factor["created_at_run"] = cfg.run_date
            factor["provenance"] = _provenance(idea, ideas, cfg)
            factor["status"] = "candidate"
            factors.append(factor)
            write_json(out_dir / f"{factor['factor_id']}.json", factor)
            write_json(library_dir / f"{factor['factor_id']}.json", factor)
    payload = {
        "agent": "factor_design",
        "run_date": cfg.run_date,
        "factors": factors,
        "skipped_factors": skipped_factors,
        "failed_memory_audit": failed_audit,
    }
    write_json(cfg.run_dir / "candidate_factors.json", payload)
    return payload


if __name__ == "__main__":
    run()
