# Quant Research System Readiness Report

Run date: 20260605
Status: not_production_ready
Readiness score: 0.69

## Checks

- run_history_present: ok
- latest_run_complete: ok
- latest_run_history_matches_run_date: ok
- latest_run_history_matches_current_outputs: ok
- latest_self_audit_pass: ok
- latest_self_audit_is_current_evidence: ok
- latest_self_audit_matches_current_outputs: ok
- latest_daily_report_is_current_evidence: fail
- latest_candidate_factor_files_match_payload: ok
- latest_factor_library_matches_candidates: ok
- latest_backtest_result_files_match_payload: ok
- latest_backtest_dataset_provenance_matches_manifest: ok
- latest_factor_database_matches_backtests: ok
- latest_failure_analysis_matches_critique: ok
- latest_next_generation_files_match_payload: ok
- latest_research_log_matches_current_outputs: ok
- latest_data_health_latest_matches_current_outputs: ok
- latest_source_snapshots_match_current_outputs: ok
- all_required_agents_seen_latest: ok
- knowledge_base_has_factors: ok
- research_log_present: ok
- latest_knowledge_pointers_match_run_date: ok
- latest_schedule_is_daily_run_daily: ok
- latest_cron_example_matches_schedule: ok
- latest_run_audit_is_current_evidence: fail
- latest_run_has_research_activity: ok
- has_365_research_activity_runs: fail
- has_365_unique_research_activity_dates: fail
- has_365_consecutive_research_activity_dates: fail
- production_evidence_dates_have_research_activity: ok
- has_365_knowledge_save_dates: fail
- has_365_consecutive_knowledge_save_dates: fail
- production_evidence_dates_have_knowledge_saves: ok
- source_snapshots_present: ok
- failure_memory_present: ok
- latest_killed_factors_have_failure_memory: ok
- latest_killed_factor_failure_memory_details_match: ok
- latest_data_is_production_evidence: ok
- latest_data_artifact_is_production_evidence: ok
- data_health_log_present: ok
- has_365_data_artifact_dates: fail
- has_365_consecutive_data_artifact_dates: fail
- production_evidence_dates_have_data_artifacts: ok
- latest_market_sources_are_production_evidence: fail
- latest_research_sources_are_production_evidence: fail
- artifact_manifest_present: ok
- artifact_manifest_matches_run_date: ok
- artifact_manifest_latest_matches_current_manifest: ok
- artifact_manifest_required_files_present: ok
- artifact_manifest_hashes_present: ok
- artifact_manifest_verification_passed: ok
- artifact_manifest_verification_matches_current_manifest: ok
- artifact_verification_latest_matches_current_verification: ok
- readiness_markdown_matches_current_json: ok
- repository_deliverables_present: ok
- run_daily_invocation_present: ok
- run_daily_invocation_success: ok
- run_daily_invocation_matches_run_date: ok
- has_365_successful_run_daily_invocations: fail
- has_365_unique_successful_run_daily_invocation_dates: fail
- has_365_consecutive_successful_run_daily_invocation_dates: fail
- production_evidence_dates_have_successful_run_daily_invocations: ok
- has_365_source_snapshot_dates: fail
- has_365_consecutive_source_snapshot_dates: fail
- production_evidence_dates_have_source_snapshots: ok
- no_jsonl_parse_errors: ok
- has_365_successful_runs: fail
- has_365_production_evidence_runs: fail
- has_365_unique_successful_run_dates: fail
- has_365_unique_production_evidence_dates: fail
- has_365_consecutive_successful_run_dates: fail
- has_365_consecutive_production_evidence_dates: fail

## Blockers

- 365-day unattended proof missing: 1/365 successful audited runs recorded
- 365 unique successful run dates missing: 1/365 unique audited dates recorded
- 365 consecutive successful run dates missing: longest streak is 1/365 days
- latest run_audit does not prove current config/lock/retention evidence: run_audit={'config': {'agent_retries': 1, 'data_root': '/home/lcc17/pan_sync_20260528', 'factor_library': 'factor_library', 'knowledge_root': 'knowledge_base', 'lock_stale_minutes': 180, 'min_free_disk_mb': 512, 'offline': True, 'output_root': 'reports', 'retention_days': 370}, 'lock': {'created_at': '2026-06-04T22:41:00.345808+00:00', 'pid': 3866620, 'recovered_stale_lock': False, 'run_date': '20260605', 'stale_after_minutes': 180, 'stale_lock_age_seconds': None}, 'run_date': '20260605', 'state': {'agents': [{'agent': 'preflight', 'attempt': 1, 'duration_sec': 0.005, 'status': 'ok'}, {'agent': 'market_intelligence', 'attempt': 1, 'duration_sec': 0.004, 'status': 'ok'}, {'agent': 'research_agent', 'attempt': 1, 'duration_sec': 0.004, 'status': 'ok'}, {'agent': 'factor_design', 'attempt': 1, 'duration_sec': 0.011, 'status': 'ok'}, {'agent': 'data_agent', 'attempt': 1, 'duration_sec': 25.624, 'status': 'ok'}, {'agent': 'backtest_agent', 'attempt': 1, 'duration_sec': 82.281, 'status': 'ok'}, {'agent': 'critic_agent', 'attempt': 1, 'duration_sec': 52.316, 'status': 'ok'}, {'agent': 'evolution_agent', 'attempt': 1, 'duration_sec': 0.013, 'status': 'ok'}, {'agent': 'knowledge_base', 'attempt': 1, 'duration_sec': 0.071, 'status': 'ok'}, {'agent': 'schedule', 'attempt': 1, 'duration_sec': 0.002, 'status': 'ok'}, {'agent': 'self_audit', 'attempt': 1, 'duration_sec': 0.007, 'status': 'ok'}, {'agent': 'readiness_report', 'attempt': 1, 'duration_sec': 1.863, 'status': 'ok'}, {'agent': 'artifact_manifest', 'attempt': 1, 'duration_sec': 2.637, 'status': 'ok'}], 'artifact_manifest_path': 'reports/daily_logs/20260605/artifact_manifest.json', 'completed_agents': ['preflight', 'market_intelligence', 'research_agent', 'factor_design', 'data_agent', 'backtest_agent', 'critic_agent', 'evolution_agent', 'knowledge_base', 'schedule', 'self_audit', 'readiness_report', 'artifact_manifest'], 'current_agent': None, 'lock': {'created_at': '2026-06-04T22:41:00.345808+00:00', 'pid': 3866620, 'recovered_stale_lock': False, 'run_date': '20260605', 'stale_after_minutes': 180, 'stale_lock_age_seconds': None}, 'readiness_report_path': 'reports/READINESS_REPORT.md', 'retention': {'removed': [], 'retention_days': 370}, 'run_date': '20260605', 'run_history_path': 'knowledge_base/run_history.jsonl', 'started_at': '2026-06-04T22:41:00.346159+00:00', 'status': 'complete', 'updated_at': '2026-06-04T22:43:45.225510+00:00'}}
- 365 active research/backtest runs missing: 1/365 runs generated ideas, candidate factors, and backtest results
- 365 unique active research/backtest dates missing: 1/365 unique dates have ideas, candidate factors, and backtests
- 365 consecutive active research/backtest dates missing: longest streak is 1/365 days
- 365 knowledge-base save dates missing: 1/365 complete knowledge saves recorded
- 365 consecutive knowledge-base save dates missing: longest streak is 1/365 days
- latest daily_report.md does not prove current run summary with required agent/file evidence
- 365 production-grade data artifact dates missing: 1/365 dates have real fresh data artifacts
- 365 consecutive production-grade data artifact dates missing: longest streak is 1/365 days
- latest market intelligence sources are offline/fallback or missing live evidence
- latest research sources are offline/fallback or missing live evidence
- 365-day production evidence missing: 0/365 runs have live sources and real fresh data
- 365 unique production-evidence dates missing: 0/365 unique dates have live sources and real fresh data
- 365 consecutive production-evidence dates missing: longest streak is 0/365 days
- 365 successful run_daily shell invocations missing: 1/365 successful invocations recorded
- 365 unique successful run_daily invocation dates missing: 1/365 unique invocation dates recorded
- 365 consecutive successful run_daily invocation dates missing: longest streak is 1/365 days
- 365 production-grade source snapshot dates missing: 0/365 dates have market and research snapshots
- 365 consecutive production-grade source snapshot dates missing: longest streak is 0/365 days

## Evidence

- total run history records: 1
- unique run dates: 1
- successful audited runs: 1
- active research/backtest runs: 1
- production evidence runs: 0
- unique successful run dates: 1
- unique active research/backtest dates: 1
- unique production evidence dates: 0
- longest successful date streak days: 1
- longest active research/backtest date streak days: 1
- longest production evidence date streak days: 0
- first run date: 20260605
- latest run date: 20260605
- factor records: 5
- research log records: 1
- knowledge save dates: 1
- longest knowledge save date streak days: 1
- source snapshot records: 2
- production-grade source snapshot dates: 0
- longest source snapshot date streak days: 0
- data health records: 1
- production-grade data artifact dates: 1
- longest data artifact date streak days: 1
- failure memory records: 4
- jsonl parse errors: 0
- jsonl quarantine dir: knowledge_base/jsonl_quarantine
- repository deliverables present: True
- repository missing files: none
- repository missing directories: none
- README documents audited readiness: True
- README missing snippets: none
- run_daily executable: True
- run_daily uses audited entrypoint: True
- artifact manifest files: 46
- artifact manifest missing required paths: none
- artifact manifest verification: pass
- artifact manifest verification matches current manifest: True
- artifact verification latest matches current verification: True
- artifact verification manifest generated at: 2026-06-04T22:43:48.845706+00:00
- artifact manifest hash mismatches: 0
- artifact manifest missing files: 0
- run_daily invocation present: True
- run_daily invocation status: success
- run_daily invocation exit_code: 0
- run_daily invocation run_date: 20260605
- run_daily expected entrypoint script: /home/lcc17/dl/run_daily.sh
- successful run_daily invocations: 1
- unique successful run_daily invocation dates: 1
- longest successful run_daily invocation date streak days: 1
- schedule cadence: daily
- schedule daily run_daily: True
- schedule cron line: 30 18 * * * cd /home/lcc17/dl && bash /home/lcc17/dl/run_daily.sh >> /home/lcc17/dl/reports/daily_cron.log 2>&1

## Latest Self Audit

- status: pass
- score: 1.0
- source_mode: offline
- data_freshness_status: ok
