from __future__ import annotations

from typing import Any

from .config import RunConfig, load_config
from .factor_design import _failed_factor_keys, factor_identity_keys, normalize_formula_key
from .io_utils import append_jsonl, ensure_dir, read_json, write_json


def _variant(
    result: dict[str, Any],
    suffix: str,
    name_suffix: str,
    formula: str,
    expression: str,
    status: str,
    rationale: str,
    critique: dict[str, Any],
) -> dict[str, Any]:
    formula_key = normalize_formula_key(formula)
    return {
        "factor_id": f"{result['factor_id']}_{suffix}",
        "parent_factor_id": result["factor_id"],
        "name": f"{result['name']} {name_suffix}",
        "formula": formula,
        "formula_key": formula_key,
        "expression": expression,
        "horizon_days": result.get("horizon_days", 5),
        "status": status,
        "rationale": rationale,
        "parent_decision": critique.get("decision", result.get("decision")),
        "failed_issues": critique.get("issues", []),
        "parent_metrics": {
            "rankic_mean": result.get("rankic_mean"),
            "rankic_ir": result.get("rankic_ir"),
            "rankic_positive_frac": result.get("rankic_positive_frac"),
            "ann_return_net": (result.get("portfolio") or {}).get("ann_return_net"),
            "turnover_mean": (result.get("portfolio") or {}).get("turnover_mean"),
            "max_drawdown": (result.get("portfolio") or {}).get("max_drawdown"),
        },
        "provenance": {
            "source": "evolution_agent",
            "parent_factor_id": result["factor_id"],
            "parent_formula_key": result.get("formula_key") or normalize_formula_key(result.get("formula")),
            "critique_checks": critique.get("checks", {}),
        },
    }


def _promote_variants(result: dict[str, Any], critique: dict[str, Any]) -> list[dict[str, Any]]:
    base_formula = result["formula"]
    expression = result["expression"]
    return [
        _variant(
            result,
            "X_COST",
            "cost-aware variant",
            f"{base_formula} * (1 - rank(turnover_20))",
            expression,
            "next_generation_candidate",
            "Promoted parent gets a lower-turnover robustness variant for cost sensitivity.",
            critique,
        ),
        _variant(
            result,
            "X_LIQ",
            "liquidity-capacity variant",
            f"{base_formula} * rank(amount_20)",
            expression,
            "next_generation_candidate",
            "Promoted parent gets an amount-filtered variant for capacity and tradability checks.",
            critique,
        ),
    ]


def _pivot_variants(result: dict[str, Any], critique: dict[str, Any]) -> list[dict[str, Any]]:
    issues = set(critique.get("issues", []))
    base_formula = result["formula"]
    expression = result["expression"]
    variants: list[dict[str, Any]] = []
    if "non_positive_rankic" in issues or "unstable_rankic" in issues:
        variants.append(_variant(
            result,
            "PIVOT_REV",
            "direction-flipped repair",
            f"1 - ({base_formula})",
            expression,
            "repair_candidate",
            "Parent signal was negative or unstable; test the opposite rank direction before abandoning the family.",
            critique,
        ))
    if "non_positive_cost_adjusted_return" in issues or "high_turnover" in issues:
        variants.append(_variant(
            result,
            "PIVOT_COST",
            "turnover-filtered repair",
            f"({base_formula}) * (1 - rank(turnover_20))",
            expression,
            "repair_candidate",
            "Parent failed cost-adjusted return or turnover; damp high-turnover names and retest.",
            critique,
        ))
    if "large_drawdown" in issues or "weak_rankic_stability" in issues or "unstable_rankic" in issues:
        variants.append(_variant(
            result,
            "PIVOT_DEF",
            "defensive interaction repair",
            f"({base_formula}) * rank(low_vol) * rank(liq_inv)",
            expression,
            "repair_candidate",
            "Parent had drawdown or stability issues; interact with defensive liquidity and low-vol filters.",
            critique,
        ))
    if not variants:
        variants.append(_variant(
            result,
            "PIVOT_INTERACT",
            "interaction pivot",
            f"({base_formula}) * rank(amount_ratio_20)",
            expression,
            "repair_or_pivot",
            "No specific repair trigger matched; require an interaction variant rather than repeating the raw formula.",
            critique,
        ))
    return variants


def _record_failure_memory(cfg: RunConfig, result: dict[str, Any], critique: dict[str, Any], children: list[dict[str, Any]]) -> None:
    if critique.get("decision") != "kill":
        return
    append_jsonl(cfg.knowledge_root / "failure_memory.jsonl", {
        "run_date": cfg.run_date,
        "factor_id": result.get("factor_id"),
        "formula": result.get("formula"),
        "formula_key": result.get("formula_key") or normalize_formula_key(result.get("formula")),
        "expression": result.get("expression"),
        "issues": critique.get("issues", []),
        "checks": critique.get("checks", {}),
        "parent_metrics": {
            "rankic_mean": result.get("rankic_mean"),
            "ann_return_net": (result.get("portfolio") or {}).get("ann_return_net"),
            "turnover_mean": (result.get("portfolio") or {}).get("turnover_mean"),
            "max_drawdown": (result.get("portfolio") or {}).get("max_drawdown"),
        },
        "next_actions": [child["factor_id"] for child in children],
    })


def _matched_failed_keys(factor: dict[str, Any], failed_keys: set[str]) -> list[str]:
    return [
        key
        for key in factor_identity_keys(
            factor.get("factor_id"),
            factor.get("formula"),
            factor.get("formula_key"),
            factor.get("expression"),
        )
        if key in failed_keys
    ]


def run(config: RunConfig | None = None) -> dict[str, Any]:
    cfg = config or load_config()
    results = read_json(cfg.run_dir / "backtest_results.json", {"results": []})
    critiques = read_json(cfg.run_dir / "critique.json", {"critiques": []})
    critique_by_id = {c["factor_id"]: c for c in critiques.get("critiques", [])}
    failed_keys, failed_audit = _failed_factor_keys(cfg)
    out_dir = ensure_dir(cfg.run_dir / "next_generation_factors")
    next_factors = []
    skipped_factors = []
    for result in results.get("results", []):
        factor_id = result["factor_id"]
        critique = critique_by_id.get(factor_id, {})
        if critique.get("decision") == "promote":
            children = _promote_variants(result, critique)
        else:
            children = _pivot_variants(result, critique)
        kept_children = []
        for child in children:
            matched_keys = _matched_failed_keys(child, failed_keys)
            if matched_keys:
                skipped_factors.append({
                    "factor_id": child["factor_id"],
                    "parent_factor_id": child.get("parent_factor_id"),
                    "formula": child.get("formula"),
                    "formula_key": child.get("formula_key"),
                    "expression": child.get("expression"),
                    "reason": "matched_failed_factor_memory",
                    "matched_keys": matched_keys,
                })
                continue
            next_factors.append(child)
            kept_children.append(child)
            write_json(out_dir / f"{child['factor_id']}.json", child)
        _record_failure_memory(cfg, result, critique, kept_children)
    payload = {
        "agent": "evolution_agent",
        "run_date": cfg.run_date,
        "next_generation_factors": next_factors,
        "skipped_evolution_factors": skipped_factors,
        "failed_memory_audit": failed_audit,
    }
    write_json(cfg.run_dir / "next_generation_factors.json", payload)
    return payload


if __name__ == "__main__":
    run()
