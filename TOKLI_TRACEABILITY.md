# TOKLI — Traceability

Chain: **evidence → requirement → spec → acceptance criterion → test**. Every requirement ID
in `specs/` appears below. Tests are *planned* (Phase 0). A requirement without a test is a
defect in this document.

Evidence codes:
- `H##` = hazard in TOKLI_EVIDENCE.md §1
- `MD-##` = machine-dependence hazard in SPEC 018
- `E5a` = measurement in TOKLI_EVIDENCE.md §2
- `Brief§n` = product brief (Phase 0 prompt) section n
- `R01§n` = PHASE0_1_REVIEW.md section n (Phase 0.1 decisions)

## Scope (SPEC 000)

| Req | Why (evidence) | AC | Tests |
|---|---|---|---|
| SC-001 | Brief§2; H38 | AC-SC-1 | `test_only_compression_transformer_registered` |
| SC-002 | Brief§2 (no BLOCK) | AC-SC-2 | `test_no_content_based_rejections` |
| SC-003 | H39 | AC-SC-3 | `test_forwarded_body_adds_no_structure` |
| SC-004 | transparency | AC-SC-4 | `test_response_bytes_identical` |
| SC-005 | H34 | AC-OB-4 | `test_default_logging_contains_no_prompt_text` |
| SC-006 | MD-02, MD-24 | AC-SC-5 | `test_no_outbound_connections_except_upstream` |
| SC-007 | quality-first (Brief§9) | AC-CM-1 | `test_passthrough_forwards_original_bytes` |

## Canonical model (SPEC 001)

| Req | Why | AC | Tests |
|---|---|---|---|
| CM-001 | transparency; H05 | AC-CM-1 | `test_passthrough_forwards_original_bytes` |
| CM-002 | H06 | AC-CM-2 | `test_render_changes_only_patched_values` |
| CM-003 | forward compatibility: unknown parts are re-emitted untouched | AC-CM-3 | `test_unknown_block_types_roundtrip` |
| CM-004 | H07 | AC-CM-2 | `test_structure_preserved_after_compression` |
| CM-005 | attribution and trace need stable ids | AC-CM-2 | `test_render_changes_only_patched_values` |
| CM-006 | H04 | AC-CM-4 | `test_tool_name_resolution_per_protocol` |
| CM-007 | fail to pass-through | AC-CM-5 | `test_malformed_body_relayed_verbatim` |
| CM-008 | cannot parse encoded bodies | AC-CM-5 | `test_content_encoded_body_relayed_verbatim` |
| CM-009 | tool schemas, `cache_control` and thinking signatures are validated or cached by providers and must never change | AC-CM-6 | `test_forbidden_parts_never_mutable` |
| CM-010 | ARCH §5 | AC-CM-7 | `test_import_contracts` |
| CM-011 | H09 (non-ASCII escaping changes bytes and length) | AC-CM-2 | `test_patched_body_utf8_and_length` |
| CM-012 | H33 | AC-CM-5 | `test_oversize_body_relayed_verbatim` |
| CM-013 | pruning needs tool history without protocol knowledge (SPEC 019) | AC-CM-4 | `test_tool_records_per_protocol` |

## Proxy (SPEC 002)

| Req | Why | AC | Tests |
|---|---|---|---|
| PX-001 | MD-09 | AC-PX-1 | `test_default_bind_is_loopback`, `test_remote_bind_requires_flag` |
| PX-002 | H32, MD-10 | AC-PX-2 | `test_routing_table`, `test_unknown_prefix_returns_tokli_404` |
| PX-003 | explicit routing table, no guessing (H32) | AC-PX-2 | `test_routing_table` |
| PX-004 | RFC 9110 hop-by-hop semantics | AC-PX-2 | `test_headers_forwarded_except_hop_by_hop` |
| PX-005 | H30 | AC-PX-3 | `test_response_bytes_identical` |
| PX-006 | Claude Code always streams; H31 | AC-PX-3 | `test_stream_chunks_identical_and_unbuffered` |
| PX-007 | H30 | AC-PX-4 | `test_upstream_errors_relayed_verbatim` |
| PX-008 | clear source of failure | AC-PX-5 | `test_upstream_unreachable_returns_tokli_502` |
| PX-009 | resource hygiene | AC-PX-6 | `test_client_disconnect_cancels_upstream` |
| PX-010 | fail to pass-through (ARCH §6) | AC-PX-7 | `test_internal_error_forwards_original` |
| PX-011 | H33 | AC-CM-5 | `test_large_body_not_rejected` |
| PX-012 | Brief§14 correlation | AC-OB-1 | `test_request_id_header` |
| PX-013 | ops | — (trivial) | `test_health_endpoint` |
| PX-014 | usage parsing needs plain bodies | AC-AN-3 | `test_headers_forwarded_except_hop_by_hop` (accept-encoding cases) |

## Anthropic (SPEC 003)

| Req | Why | AC | Tests |
|---|---|---|---|
| AN-001 | Brief§24 example | AC-AN-1 | compat suite `tests/compat/anthropic/*` |
| AN-002 | tool results nested in user-role `tool_result` blocks must be reachable (SPEC 003 rationale) | AC-AN-1 | `test_anthropic_segment_mapping` |
| AN-003 | H04 | AC-AN-2 | `test_anthropic_tool_name_resolution` |
| AN-004 | `cache_control` preservation; H05, H07 | AC-AN-1 | `test_anthropic_block_attributes_preserved`, `test_anthropic_cache_control_count_preserved` |
| AN-005 | H20 | AC-AN-3 | `test_anthropic_usage_non_stream` |
| AN-006 | same; streaming default | AC-AN-3, AC-AN-4 | `test_anthropic_usage_stream`, `test_anthropic_usage_stream_with_error_event` |
| AN-007 | telemetry never breaks traffic | AC-AN-3 | `test_usage_parser_failure_is_unavailable` |
| AN-008 | Claude Code calls count_tokens; Q4 | AC-AN-5 | `test_anthropic_other_endpoints_verbatim` |
| AN-009 | bounded memory | AC-AN-4 | `test_usage_parser_memory_bounded` |

## OpenAI Chat (SPEC 004)

| Req | Why | AC | Tests |
|---|---|---|---|
| OC-001 | Brief§1 | AC-OC-1 | compat suite `tests/compat/openai_chat/*` |
| OC-002 | tool output lives in `role:"tool"` messages (SPEC 004 rationale) | AC-OC-2 | `test_chat_segment_mapping`, `test_chat_tool_messages_are_mutable` |
| OC-003 | verbatim hazard | AC-OC-2 | `test_chat_tool_name_resolution` |
| OC-004 | transparency of stream shape | AC-OC-3 | `test_chat_stream_options_untouched` |
| OC-005 | usage | AC-OC-4 | `test_chat_usage_non_stream` |
| OC-006 | usage only if the client asked | AC-OC-4 | `test_chat_usage_stream_with_include_usage`, `test_chat_usage_stream_without_include_usage_unavailable` |
| OC-007 | SSE robustness | AC-OC-4 | `test_chat_usage_stream_with_include_usage` |

## OpenAI Responses (SPEC 005)

| Req | Why | AC | Tests |
|---|---|---|---|
| OR-001 | Codex traffic shapes, Windows and Unix (MD-13) | AC-OR-1, AC-OR-3 | compat suite `tests/compat/openai_responses/*`, `test_responses_segment_mapping`, `test_responses_reasoning_untouched` |
| OR-002 | tool-output item types share the `call_id` + `output` shape (SPEC 005 rationale) | AC-OR-2 | `test_responses_tool_output_detected_by_shape` |
| OR-003 | verbatim hazard | AC-OR-1 | `test_responses_tool_name_resolution` |
| OR-004 | stateful API | AC-OR-1 | `test_responses_previous_response_id_passthrough` |
| OR-005 | usage | AC-OR-1 | `test_responses_usage_non_stream`, `test_responses_usage_stream_completed` |
| OR-006 | usage robustness | AC-OR-1 | `test_responses_usage_stream_failed_unavailable` |
| (determinism) | prefix determinism keeps provider caching intact (H05) | AC-OR-4 | `test_growing_conversation_prefix_stays_identical` |

## Upstream & auth (SPEC 006)

| Req | Why | AC | Tests |
|---|---|---|---|
| UP-001 | explicit upstream configuration, reported by doctor | AC-PT-2 | `test_doctor_report_fields` |
| UP-002 | H35 | AC-UP-1 | `test_passthrough_forwards_client_credentials` |
| UP-003 | Brief§1 OpenAI API key required | AC-UP-2 | `test_inject_replaces_client_credentials` |
| UP-004 | fail-closed on credentials | AC-UP-3 | `test_missing_inject_credential_returns_503` |
| UP-005 | H36, MD-06 | AC-UP-2 | `test_no_cross_provider_credentials`, `test_inject_uses_only_configured_source`, `test_inherited_provider_env_is_ignored_unless_configured` |
| UP-006 | H34 | AC-UP-4 | `test_logs_never_contain_credentials` |
| UP-007 | H37, MD-14 | AC-UP-5 | `test_key_file_with_bom_is_accepted`, `test_utf16_key_file_reported` |
| UP-008 | security hygiene | — | `test_tls_verification_default_on` |
| UP-009 | long streams | — | `test_read_timeout_between_chunks` |
| UP-010 | auth ≠ transformation (Brief§4) | AC-UP-6 | `test_body_independent_of_auth_mode` |

## Pipeline (SPEC 007)

| Req | Why | AC | Tests |
|---|---|---|---|
| PL-001 | H38 | AC-PL-3 | `test_stage_order_from_config` |
| PL-002 | H38: ordering rules are checks, not comments; R01§C (C1) | AC-PL-1 | `test_invalid_stage_order_fails_startup` |
| PL-003 | separation of analysis/transformation | AC-PL-4 | `test_analyzer_cannot_patch` |
| PL-004 | chaining | AC-PL-3 | `test_patches_visible_to_later_stages` |
| PL-005 | H38: isolation implemented once | AC-PL-2 | `test_stage_exception_isolated`, `test_stage_timeout_isolated` |
| PL-006 | Brief§14 timings | AC-OB-2 | `test_trace_contains_all_spans` |
| PL-007 | Brief§16 redaction seam | AC-PL-3 | `test_new_transformer_needs_no_adapter_change` |
| PL-008 | Claude Code injects `<system-reminder>` blocks (SPEC 003 rationale) | AC-PL-3 | `test_reminder_spans_protected` |

## Token measurement (SPEC 008)

| Req | Why | AC | Tests |
|---|---|---|---|
| TM-001 | H20 | AC-TM-1 | `test_token_counts_stable_fixture` |
| TM-002 | model-dependent tokenizers | AC-TM-1 | `test_tokenizer_selected_by_model_map` |
| TM-003 | Brief§10 exact vs estimate | AC-AN-3 | `test_anthropic_usage_non_stream` (and per protocol) |
| TM-004 | H21 | AC-TM-5 | `test_calibration_factor` |
| TM-005 | Brief§10 "never present an estimate as exact" | AC-TM-4 | `test_every_api_token_field_has_method` |
| TM-006 | MD-02 | AC-TM-2 | `test_missing_tokenizer_fails_with_actionable_message`, `test_tampered_tokenizer_is_reported` |
| TM-007 | MD-02, MD-20 | AC-TM-3 | `test_import_has_no_side_effects`, `test_starts_offline_with_provisioned_tokenizer` |
| TM-008 | Brief§19 | AC-TM-1 | `test_fingerprint_equal_across_os` |
| TM-009 | tokenizer drift detection | AC-TM-5 | `test_calibration_outlier_falls_back_to_estimate` |
| TM-010 | MD-02; Q7 decision (S0 review P2) | AC-TM-6 | `test_setup_tokenizers_verifies_sha256`, `test_setup_tokenizers_from_file`, `test_setup_tokenizers_refuses_tampered_download`, `test_setup_tokenizers_from_file_rejects_unknown_file`, `test_setup_tokenizers_from_file_never_downloads_missing_ones`, `test_required_tokenizers`, `test_catalog_entries_are_pinned`, `test_check_tokenizer_states`, `test_setup_tokenizers_cli_refuses_unknown_file` |

## Compression core (SPEC 009)

| Req | Why | AC | Tests |
|---|---|---|---|
| CC-001 | H13 | AC-CC-9 | `test_registry_contract_every_lossless_has_roundtrip_property` |
| CC-002 | Brief§7; H01, H02 | AC-CC-1 | `test_lossless_only_never_runs_lossy_compressor`, `test_lossy_allowed_runs_selective_and_lossy`, `test_unknown_requires_explicit_enable` |
| CC-003 | Brief§8 enabled ≠ forced | AC-CC-2 | `test_enabled_compressor_not_applied_when_not_applicable` |
| CC-004 | Brief§10; tokenizer mismatch margin | AC-CC-3 | `test_longer_output_rejected` |
| CC-005 | Brief§10 invariant | AC-CC-3 | `prop_compression_never_increases_tokens` |
| CC-006 | determinism; H05 | AC-CC-4 | `prop_compression_is_deterministic`, `test_segment_output_independent_of_other_segments` |
| CC-007 | reminders; future redaction markers | AC-CC-5 | `prop_protected_spans_preserved` |
| CC-008 | H14, MD-25 | AC-CC-6 | `test_compressor_exception_is_recorded`, `test_compressor_timeout_is_recorded` |
| CC-009 | H13 | AC-CC-8 | `test_chain_order_by_stage_then_id`, `test_terminal_stops_chain` |
| CC-010 | H14, MD-03 | AC-CC-7 | `test_missing_dependency_marks_compressor_unavailable` |
| CC-011 | Brief§6 | AC-CC-9 | `test_registry_contract_every_lossless_has_roundtrip_property` |
| CC-012 | Brief§11 | AC-CC-8 | `test_compressor_stats_expected_fixture`, `prop_marginal_savings_sum_to_total` |
| CC-013 | Brief§11 skip reasons | AC-CC-8 | `test_compressor_stats_expected_fixture` |
| CC-014 | Brief§9 cheap before expensive; E9; R01§9 (budget = runtime control, provisional default) | AC-CC-8 | `test_budget_exhaustion_skips` |
| CC-015 | H02: lossless is proven by a decoder | AC-CC-9 | `test_registry_contract_every_lossless_has_roundtrip_property` |
| CC-016 | defence in depth | AC-CC-9 | `test_verify_lossless_rejects_decode_mismatch` |
| CC-017 | ARCH §5 | AC-CM-7 | `test_import_contracts` |
| CC-018 | superseding rewrites sent history (SPEC 019) | AC-PR-6 | `test_history_rewritten_flag` |
| CC-019 | R01§3, §6: a reference is only as good as its target | AC-CC-10, AC-PR-8 | `test_reference_target_integrity_enforced`, `test_superseded_rejected_on_reference_target` |
| CC-020 | R01§2, §7: policy eligibility ≠ default enablement; every transformation relies on model behaviour | AC-CC-11 | `test_every_compressor_declares_assumptions`, `test_registry_default_enabled_requires_eval_record` |
| CC-021 | R01§3: verbatim hazard does not apply where the bytes stay verbatim in the target | AC-CC-12, AC-PR-9 | `test_verbatim_tools_exempt_only_reference_equivalence`, `test_duplicate_pruning_applies_to_verbatim_tools` |

## Tool-history pruning (SPEC 019)

| Req | Why | AC | Tests |
|---|---|---|---|
| PR-001 | E5a: pruning reached 38.9 % as an upper reference (TOKLI_EVIDENCE §2); request-level reasoning needed | AC-PR-1 | `test_request_scope_runs_before_segment_scope`, `test_duplicate_results_stub_later_copies` |
| PR-002 | E5a: exact duplicates ≈ 1.1 %; product owner: duplicates must be lossless | AC-PR-1 | `test_duplicate_results_stub_later_copies`, `test_duplicate_require_same_call_option` |
| PR-003 | lossless by reference (CC classification) | AC-PR-1 | `prop_duplicate_pruning_decodes_whole_request`, `test_duplicate_pruning_never_stubs_first_occurrence` |
| PR-004 | H05 | AC-PR-2 | `test_duplicate_pruning_prefix_stable_across_turns` |
| PR-005 | H07, H08 | AC-PR-3 | `test_pruning_preserves_structure_and_arguments` |
| PR-006 | client-specific tool meaning is data, not code | AC-PR-4 | `test_tool_semantics_from_config_only`, `test_unknown_tool_never_superseded`, `test_shell_command_classification_rules`, `test_path_normalisation` |
| PR-007 | E5a: 75 % of pruned entries touched a re-touched file | AC-PR-5 | `test_superseded_read_stubbed_after_full_reread`, `test_edit_never_supersedes`, `test_partial_read_ranges`, `test_superseded_respects_age_and_min_saving` |
| PR-008 | keep the current state visible | AC-PR-4 | `test_unknown_tool_never_superseded`, `test_edit_never_supersedes` |
| PR-009 | H05 | AC-PR-6 | `test_history_rewritten_flag` |
| PR-010 | avoid wasted work: prune before compressing text | AC-PR-1 | `test_pruning_runs_before_segment_compressors` |
| PR-011 | CM-009 / AN-004 | AC-PR-3 | `test_stub_preserves_cache_control_and_is_error` |
| PR-012 | R01§3 reference integrity; stubs never chain | AC-PR-8 | `test_duplicate_stub_names_earliest_copy`, `test_superseded_rejected_on_reference_target` |
| PR-013 | R01§3; E5a: 75 % of pruned entries touched a re-read file | AC-PR-9 | `test_duplicate_pruning_applies_to_verbatim_tools` |
| PR-014 | shell-command classification defined in the spec; Codex Windows/Unix shapes (MD-13) | AC-PR-10 | `test_shell_command_classification_rules` |

## Compressors (SPEC 010)

| Req | Why | AC (in spec) | Tests |
|---|---|---|---|
| CP-JM-001 | pretty-printed JSON is common in tool output; expected range in TOKLI_EVIDENCE §2 | json_minify tests | `prop_json_minify_decode_roundtrip` |
| CP-JM-002 | H09 | " | `test_json_minify_preserves_number_spelling`, `test_json_minify_preserves_duplicate_keys` |
| CP-JM-003 | pass-through preference | " | `test_json_minify_not_applicable_on_mixed_text`, `test_json_minify_rejects_nan` |
| CP-JM-004 | H04 | " | `test_json_minify_skipped_for_verbatim_tool` |
| CP-JM-005 | correctness constraint: linear time (R01§9) | " | `test_json_minify_linear_time` |
| CP-SG-001 | grep output repeats the path on every match line | search_group tests | `prop_search_group_decode_roundtrip` |
| CP-SG-002 | H02, H03 | " | `test_search_group_keeps_unparsed_lines_in_place` |
| CP-SG-003 | H03, MD-11 | " | `test_search_group_windows_paths_roundtrip` |
| CP-SG-004 | MD-12 | " | `test_search_group_crlf_roundtrip`, `test_search_group_escaping` |
| CP-DI-001 | dictionary evidence in TOKLI_EVIDENCE §2; algorithm fully specified (R01§B) | dictionary tests | `prop_dictionary_decode_roundtrip`, `test_dictionary_selection_deterministic_tie_break`, `test_dictionary_nested_symbol_decode_order`, `test_dictionary_no_gain_not_applied` |
| CP-DI-002 | symbols colliding with input text would make decoding ambiguous | " | `test_dictionary_collision_guard` |
| CP-DI-003 | lossless by decoder | " | `prop_dictionary_decode_roundtrip` |
| CP-DI-004 | substitution inside protected spans, URLs or quoted strings corrupts them | " | `test_dictionary_does_not_touch_urls_or_protected_spans` |
| CP-DT-001 | retention contract of the selective diff trim | diff tests | `test_diff_trim_preserves_changed_lines`, `test_diff_trim_preserves_headers` |
| CP-DT-002 | H10 | " | `test_diff_trim_does_not_swallow_trailing_text` |
| CP-DT-003 | honesty to the model | " | `test_diff_trim_omission_note` |
| CP-DT-004 | H11 | " | `test_diff_trim_false_positive_shapes` |
| CP-LF-001 | retention contract of the selective log filter | log tests | `test_log_filter_keeps_error_and_warn`, `test_log_filter_keeps_unleveled_lines`, `test_log_filter_order_preserved` |
| CP-LF-002 | safety gate | " | `test_log_filter_gate` |
| CP-LF-003 | honesty to the model | " | `test_log_filter_omission_note` |
| CP-LF-004 | selection rules defined in Tokli terms (R01§B) | " | `test_log_filter_normalisation_and_sampling`, `test_log_filter_mixed_keywords_kept_as_severe` |

## Routing (SPEC 011)

| Req | Why | AC | Tests |
|---|---|---|---|
| RT-001 | cheap structural features; H11 | AC-RT-1 | `test_features_linear_time`, `test_grep_feature_windows_paths` |
| RT-002 | Brief§9 cheap first | AC-RT-2 | `test_cheap_filters_before_applicable` |
| RT-003 | Brief§9 prefer pass-through | AC-RT-3 | `test_prose_only_request_passthrough` |
| RT-004 | Brief§9 | AC-RT-2 | `test_cheap_filters_before_applicable` |
| RT-005 | H12 | AC-RT-4 | `test_routing_inputs_closed_and_no_ml` |
| RT-006 | Brief§14 "why" | AC-RT-2 | `test_trace_shows_routing_counts` |

## Quality evaluation (SPEC 012)

| Req | Why | AC | Tests |
|---|---|---|---|
| QE-001 | H23: harnesses that bypass the real pipeline | AC-QE-3 | `test_harness_uses_real_pipeline` |
| QE-002 | Brief§21 | AC-QE-3 | `test_harness_report_provenance` |
| QE-003 | H23: one case per category | AC-QE-1 | `test_harness_insufficient_data` |
| QE-004 | H23: metrics that normalise away removed content | AC-QE-2 | `test_harness_detects_destructive_compressor` |
| QE-005 | reproducibility | AC-QE-3 | `test_harness_report_provenance` |
| QE-006 | default-enable gate | release checklist | (process) + `test_registry_default_enabled_requires_eval_record` |
| QE-007 | H23: constant or fabricated scores | AC-QE-1 | `test_harness_insufficient_data` |
| QE-008 | marginal vs isolated (TELEMETRY §2) | AC-QE-3 | `test_harness_identity_ci_contains_zero` (+ isolated/chained report fields) |
| QE-009 | Q11 decision: eval budget belongs to the user | AC-QE-4 | `test_eval_requires_confirmation_or_max_cost` |
| QE-010 | same; no surprise spend | AC-QE-4 | `test_eval_stops_at_cost_cap` |
| QE-011 | same; never automatic | AC-QE-4 | `test_eval_never_auto_starts`, `test_eval_requires_max_calls_without_pricing` |
| QE-012 | R01§8: behaviour-dependent defaults arrive in S4, before the S8 harness | AC-QE-5 | `test_smoke_arms_differ_only_in_candidate` |
| QE-013 | R01§8: one case format for smoke and full tiers; test-data hygiene | AC-QE-6 | `test_eval_cases_lint` |
| QE-014 | R01§8 deterministic recording of configuration, saving and outcome | AC-QE-3 | `test_harness_report_provenance` |
| QE-015 | R01§8: explicit, honest verdict rule | AC-QE-5 | `test_smoke_verdict_rule`, `test_smoke_insufficient_data` |
| QE-016 | R01§7: CC-020 needs a machine-readable record | AC-QE-7 | `test_eval_record_schema_and_provisional_rule`, `test_eval_record_invalidated_by_version_bump` |
| QE-017 | the harness must prove it can detect damage | AC-QE-2 | `test_smoke_harness_self_test` |

## Telemetry & cost (SPEC 013)

| Req | Why | AC | Tests |
|---|---|---|---|
| TC-001 | Brief§11/§14 | AC-TC-1 | `test_request_record_persisted_per_outcome` |
| TC-002 | Brief§11 | AC-TC-1 | `test_compressor_stats_only_for_considered` |
| TC-003 | Brief§11 attribution | AC-TC-2 | `prop_marginal_savings_sum_to_total` |
| TC-004 | Brief§12; H05, H22 | AC-TC-3 | `test_cost_proportional_estimate_and_bounds` |
| TC-005 | Brief§12 "never fabricate" | AC-TC-4 | `test_cost_unavailable_without_price` |
| TC-006 | honest fallback | AC-TC-3 | `test_cost_assumes_uncached_without_usage` |
| TC-007 | Brief§12 claim only affected categories | AC-TC-3 | `test_no_output_savings_claimed` |
| TC-008 | H22 | AC-TC-5 | `test_price_effective_dates` |
| TC-009 | Brief§12 pricing ≠ compression | AC-CM-7 | `test_import_contracts` |
| TC-010 | Brief§15 retention | AC-TC-1 | `test_retention_pruning` |
| TC-011 | telemetry must not break traffic | AC-TC-6 | `test_sink_failure_degrades_not_breaks` |
| TC-012 | additive migrations keep older data readable | AC-TC-1 | `test_schema_migration_forward` |
| TC-013 | R01§9: measure overhead from the first useful slice; target ≠ gate | AC-TC-7 | `test_overhead_percentiles_by_bucket`, `test_target_is_reference_not_status` |
| TC-014 | PR-009 flag was not in the record schema (R01§10 consistency pass) | AC-TC-8 | `test_request_record_pruning_fields` |

## Observability (SPEC 014)

| Req | Why | AC | Tests |
|---|---|---|---|
| OB-001 | Brief§14 | AC-OB-1 | `test_request_id_propagates_everywhere` |
| OB-002 | Brief§14 timings | AC-OB-2 | `test_trace_contains_all_spans` |
| OB-003 | "diagnose without a debugger" | AC-OB-3 | `test_trace_buffer_bounded` |
| OB-004 | Brief§14 decisions | AC-RT-2 | `test_reason_codes_closed_set` |
| OB-005 | provider support cases | AC-OB-1 | `test_upstream_correlation_ids_recorded` |
| OB-006 | H31 | AC-OB-4 | `test_upstream_error_logging_respects_content_rule` |
| OB-007 | H34 | AC-OB-4 | `test_logs_never_contain_credentials` |
| OB-008 | Brief§15 | AC-OB-4 | `test_default_logging_contains_no_prompt_text` |
| OB-009 | Brief§15 explicit, visible debug | AC-OB-5 | `test_debug_content_requires_both_switches`, `test_debug_content_banner_visible`, `test_debug_content_ttl_and_cap` |
| OB-010 | ops | AC-OB-1 | `test_request_summary_log_line` |
| OB-011 | degraded visibility | AC-TC-6 | `test_health_degraded_conditions` |

## Application API (SPEC 015)

| Req | Why | AC | Tests |
|---|---|---|---|
| API-001 | Brief§13 no content | AC-API-2 | `test_api_returns_no_content_or_credentials` |
| API-002 | Brief§10/§12 labelling | AC-API-1 | `test_every_api_token_field_has_method`, `test_api_contract_schemas` |
| API-003 | Brief§13 breakdowns | AC-API-1 | `test_metrics_filters_validated` |
| API-004 | replaceable UI (Brief§4) | AC-API-1 | `test_api_contract_schemas` |
| API-005 | config ownership (ARCH §7) | AC-API-3 | `test_patch_pinned_key_conflict`, `test_patch_unknown_key_rejected` |
| API-006 | H40 | AC-API-4 | `test_mutation_rejects_foreign_origin` |
| API-007 | atomic config | AC-API-5 | `test_config_change_atomic_snapshot` |
| API-008 | UI ↛ internals | AC-CM-7 | `test_import_contracts` |

## Dashboard (SPEC 016)

| Req | Why | AC | Tests |
|---|---|---|---|
| UI-001 | Brief§8, §13 | AC-UI-1 | `test_ui_has_no_compressor_specific_code` |
| UI-002 | Brief§10/§12 | AC-UI-2 | `test_ui_renders_method_labels` |
| UI-003 | Brief§8 kind visibility; R01§3 equivalence and assumptions visible | AC-UI-2 | `test_ui_renders_method_labels` (kind badges asserted), `test_ui_shows_equivalence_assumptions_and_eval_status` |
| UI-004 | Brief§7/§8 policy semantics | AC-UI-3 | `test_ui_policy_marks_non_lossless_not_permitted`, `test_ui_toggle_patches_config` |
| UI-005 | config ownership | AC-UI-3 | `test_ui_locked_settings_show_source` |
| UI-006 | H41, MD-21 | AC-UI-4 | `test_wheel_contains_ui_assets`, `test_ui_assets_load_offline` |
| UI-007 | Brief§15 | AC-OB-5 | `test_debug_content_banner_visible` |
| UI-008 | usability | AC-UI-2 | Playwright viewport case in `test_ui_renders_method_labels` |
| UI-009 | R01§9: expensive compressors visible and controllable | AC-UI-2 | `test_ui_overhead_target_is_reference_line` |
| UI-010 | R01§5: exact meaning of the user-facing policies | AC-UI-2 | `test_ui_policy_explanations_text` |

## Configuration (SPEC 017)

| Req | Why | AC | Tests |
|---|---|---|---|
| CF-001 | MD-05 | AC-CF-1 | `test_env_overrides_file_for_every_key`, `test_cli_overrides_env`, `test_ui_override_only_when_not_pinned`, `test_set_flag_overrides_env`, `test_defaults_when_no_layers`, `test_config_file_found_in_config_dir` |
| CF-002 | Brief§18 inspectable | AC-CF-1 | `test_config_show_reports_sources` |
| CF-003 | fail clearly (Brief§18) | AC-CF-2 | `test_unknown_key_rejected_with_layer`, `test_unknown_section_rejected`, `test_invalid_value_names_layer_key_and_expected_type`, `test_explicit_config_file_must_exist`, `test_set_requires_key_equals_value` |
| CF-004 | MD-04, MD-08 | AC-CF-3 | `test_cwd_config_and_dotenv_ignored` |
| CF-005 | mid-request consistency | AC-API-5 | `test_config_snapshot_immutable` |
| CF-006 | fingerprint + telemetry | AC-CF-4 | `test_config_hash_stable_and_sensitive` |
| CF-007 | H12, H14: no silent substitution | AC-CC-7 | `test_optional_capability_never_silently_substituted` |
| CF-008 | MD-04, MD-07 | AC-PT-2 | `test_data_dir_resolution_per_platform`, `test_config_dir_resolution_per_platform`, `test_linux_xdg_fallbacks_use_home`, `test_missing_home_fails_clearly` |
| CF-009 | Brief§8 UI | AC-API-3 | `test_patch_unknown_key_rejected` |
| CF-010 | credential hygiene | AC-CF-5 | `test_secret_values_rejected_in_config` |
| CF-011 | MD-05; S0 review M2, X2 | AC-CF-6 | `test_env_json_value_errors_name_variable`, `test_reserved_env_vars_only` |
| CF-012 | S0 review M1 (YAML implicit types, duplicate keys) | AC-CF-7 | `test_duplicate_yaml_key_rejected`, `test_yaml_implicit_types_rejected`, `test_empty_config_file_is_an_empty_layer` |

## Portability & diagnostics (SPEC 018)

| Req | Why | AC | Tests |
|---|---|---|---|
| PT-001 | Brief§19 | AC-PT-1 | `test_fingerprint_equal_across_os` |
| PT-002 | Brief§24 example; MD-04…MD-08 | AC-PT-1 | `test_behaviour_independent_of_cwd`, `test_temp_home_clean_start`, `test_hostile_environment_ignored` |
| PT-003 | MD-02, MD-24 | AC-PT-3 | `test_no_outbound_connections_except_upstream` |
| PT-004 | MD-18 | AC-PT-1 | CI matrix + `test_doctor_reports_python_version` |
| PT-005 | Brief§20 | AC-PT-2 | `test_doctor_report_fields` |
| PT-006 | Brief§20 "explain differences" | AC-PT-5 | `test_fingerprint_explain_config_difference`, `test_fingerprint_explain_tokenizer_difference` |
| PT-007 | Brief§20 never expose secrets | AC-PT-2 | `test_doctor_never_prints_secrets` |
| PT-008 | fail clearly | AC-PT-4 | `test_port_in_use_fails_clearly`, `test_unwritable_data_dir_fails_clearly`, `test_missing_tokenizer_fails_with_actionable_message`, `test_alternative_port` |
| PT-009 | MD-12 | per-compressor | `test_json_minify_crlf_roundtrip`, `test_search_group_crlf_roundtrip`, … |
| PT-011 | MD-01…MD-28 (SPEC 018 checklist) | AC-PT-6 | `test_no_dotenv_loading`, `test_cli_output_encodable_cp1252`, `test_daily_rollup_respects_tz_param`, `test_wheel_imports_tokli_in_clean_venv`, `test_no_module_reads_cwd_relative_paths` (+ the tests named per row), `test_machine_dependence_checklist_tests_exist`, `test_starts_offline_with_provisioned_tokenizer` |
| PT-012 | S0 review X1, M3 (exit criterion, doctor exit code) | AC-PT-7, AC-PT-4 | `test_doctor_normalised_snapshot`, `test_doctor_makes_no_network_calls`, `test_invalid_config_fails_clearly`, `test_doctor_normalised_snapshot_provisioned`, `test_doctor_exit_codes`, `test_unwritable_data_dir_reported` |
| PT-010 | MD-27 | AC-PT-1 | `test_fixtures_contain_no_developer_paths` |

## Hazard view: evidence → requirements

| Hazard (TOKLI_EVIDENCE.md) | Requirements |
|---|---|
| H01 Word-deletion "prose compression" corrupts code | not in v1 (TOKLI_SCOPE deferred); CC-002, CC-015 |
| H02 "Lossless" as a label, not a property | CC-001, CC-002, CC-015, CC-016 |
| H03 Search-output grouping loses data | CP-SG-002, CP-SG-003 |
| H04 Verbatim-quoting hazard | CM-006, AN-003, CP-JM-004, CC-021, E8, E11 |
| H05 Rewriting already-sent history breaks prompt caching | CM-001, CC-006, CC-018, PR-004, PR-009, TC-004 |
| H06 Flattening corrupts conversations | CM-002 |
| H07 Reordering or merging blocks breaks protocol rules | CM-004, AN-004, PR-005 |
| H08 Structural removal needs atomicity knowledge | PR-005, E10 |
| H09 Parse-and-dump changes JSON | CP-JM-002, CM-011 |
| H10 Diff detectors swallow trailing text | CP-DT-002 |
| H11 Structural detectors fire on look-alike text | RT-001, CP-DT-004 |
| H12 Routing on markers or optional models is unstable | RT-005, CF-007, PT-001 |
| H13 Strategy dispatch by conditionals | CC-001, CC-009, CC-011 |
| H14 Silent identity on failure | CC-008, CC-010 |
| H20 One tokenizer for every model, provider usage ignored | TM-001, TM-003, TM-005, AN-005 |
| H21 Mismatched measurement bases | TM-004, TM-005, TC-003 |
| H22 Flat-price cost | TC-004, TC-006, TC-008 |
| H23 Evaluation pitfalls | QE-001, QE-003, QE-004, QE-007, TC-005 |
| H30 Changed upstream errors | PX-005, PX-007 |
| H31 Buffered or silent streams | PX-006, OB-006 |
| H32 Guessing the provider | PX-002 |
| H33 Limits the provider does not impose | CM-012, PX-011 |
| H34 Credential and content leakage | SC-005, UP-006, OB-007, OB-008 |
| H35 Client keys refused | UP-002 |
| H36 Implicit credential discovery | UP-005 |
| H37 Key files with BOM or UTF-16 | UP-007 |
| H38 Mixed responsibilities | SC-001, PL-001, PL-002, PL-005 |
| H39 Structure injected into requests | SC-003 |
| H40 Unprotected admin endpoints | API-006 |
| H41 UI that needs a build step | UI-006 |
| E5a pruning upper reference, 75 % repeated files | PR-001…PR-014, E2-ext, E10, E11 |
| MD-01…MD-28 | SPEC 018 checklist, PT-011 |

## Phase 0.1 review → requirements

| Review decision (PHASE0_1_REVIEW.md) | Requirements |
|---|---|
| Preservation model: proven vs assumed (§2–§7) | CC-002, CC-015, CC-019, CC-020, CC-021, PR-012, PR-013, UI-003, UI-010 |
| Smoke evaluation tier in S2.5 (§8) | QE-003 (scoped to full tier), QE-006, QE-012…QE-017, CC-020 |
| Performance: target vs constraint vs budget (§9) | CC-014, CP-JM-005, AC-RT-1, TC-013, UI-009, TOKLI_TEST_STRATEGY §8 |
| Legacy-reference audit of specs/ (§B) | PX-004, PR-014, CP-DI-001, CP-DT-004, CP-LF-004, AC-OC-2, AC-OR-4, AC-RT-4, SPEC 007 reminder matching, SPEC 000 non-goals via TOKLI_SCOPE |
