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
| CM-001 | transparency; H05 | AC-CM-1 | `test_passthrough_forwards_original_bytes`, `test_passthrough_forwards_original_bytes (unit and end to end)` |
| CM-002 | H06 | AC-CM-2 | `test_render_changes_only_patched_values`, `test_only_json_tool_results_of_non_verbatim_tools_change` |
| CM-003 | forward compatibility: unknown parts are re-emitted untouched | AC-CM-3 | `test_unknown_block_types_roundtrip` |
| CM-004 | H07 | AC-CM-2 | `test_structure_preserved_after_compression` |
| CM-005 | attribution and trace need stable ids | AC-CM-2 | `test_render_changes_only_patched_values` |
| CM-006 | H04 | AC-CM-4 | `test_tool_name_resolution_per_protocol`, `test_anthropic_tool_name_resolution` |
| CM-007 | fail to pass-through | AC-CM-5 | `test_malformed_body_relayed_verbatim`, `test_malformed_body_raises_parse_error` |
| CM-008 | cannot parse encoded bodies | AC-CM-5 | `test_content_encoded_body_relayed_verbatim` |
| CM-009 | tool schemas, `cache_control` and thinking signatures are validated or cached by providers and must never change | AC-CM-6 | `test_forbidden_parts_never_mutable`, `test_opaque_parts_not_exposed`, `test_mutable_kinds_from_config` |
| CM-010 | ARCH §5 | AC-CM-7 | `test_import_contracts` |
| CM-011 | H09 (non-ASCII escaping changes bytes and length) | AC-CM-2 | `test_patched_body_utf8_and_length` |
| CM-012 | H33 | AC-CM-5 | `test_oversize_body_relayed_verbatim`, `test_large_body_not_rejected` |
| CM-013 | pruners need tool history without protocol knowledge | AC-PR-1 | `test_tool_records_exposed_read_only` |

## Proxy (SPEC 002)

| Req | Why | AC | Tests |
|---|---|---|---|
| PX-001 | MD-09 | AC-PX-1 | `test_default_bind_is_loopback`, `test_remote_bind_requires_flag`, `test_serve_remote_bind_needs_flag`, `test_loopback_names` |
| PX-002 | H32, MD-10 | AC-PX-2 | `test_routing_table`, `test_unknown_prefix_returns_tokli_404` |
| PX-003 | explicit routing table, no guessing (H32) | AC-PX-2 | `test_routing_table` |
| PX-004 | RFC 9110 hop-by-hop semantics | AC-PX-2 | `test_headers_forwarded_except_hop_by_hop`, `test_hop_by_hop_includes_connection_listed` |
| PX-005 | H30 | AC-PX-3 | `test_response_bytes_identical` |
| PX-006 | Claude Code always streams; H31 | AC-PX-3 | `test_stream_chunks_identical_and_unbuffered` |
| PX-007 | H30 | AC-PX-4 | `test_upstream_errors_relayed_verbatim` |
| PX-008 | clear source of failure | AC-PX-5 | `test_upstream_unreachable_returns_tokli_502`, `test_upstream_timeout_returns_tokli_504` |
| PX-009 | resource hygiene | AC-PX-6 | `test_client_disconnect_cancels_upstream` |
| PX-010 | fail to pass-through (ARCH §6) | AC-PX-7 | `test_internal_error_forwards_original` |
| PX-011 | H33 | AC-CM-5 | `test_large_body_not_rejected` |
| PX-012 | Brief§14 correlation | AC-OB-1 | `test_request_id_header`, `test_request_id_header_can_be_disabled` |
| PX-013 | ops | — (trivial) | `test_health_endpoint` |
| PX-014 | usage parsing needs plain bodies | AC-AN-3 | `test_transformable_request_asks_identity_encoding`, `test_verbatim_route_keeps_client_accept_encoding` |
| PX-015 | one large request must not stall other streams (S4.5 D3) | AC-PX-8 | `test_slow_transform_does_not_stall_other_streams` (S4.5) |

## Anthropic (SPEC 003)

| Req | Why | AC | Tests |
|---|---|---|---|
| AN-001 | Brief§24 example | AC-AN-1 | compat suite `tests/compat/anthropic/*`, `test_passthrough_forwards_original_bytes`, `test_only_json_tool_results_of_non_verbatim_tools_change`, `test_expected_changes_in_tool_use_fixture`, `test_claude_code_like_reminders_protected` |
| AN-002 | tool results nested in user-role `tool_result` blocks must be reachable (SPEC 003 rationale) | AC-AN-1 | `test_anthropic_segment_mapping`, `test_system_segments` |
| AN-003 | H04 | AC-AN-2 | `test_anthropic_tool_name_resolution` |
| AN-004 | `cache_control` preservation; H05, H07 | AC-AN-1 | `test_anthropic_block_attributes_preserved`, `test_anthropic_cache_control_count_preserved` |
| AN-005 | H20 | AC-AN-3 | `test_anthropic_usage_non_stream`, `test_anthropic_usage_non_stream_without_cache_split`, `test_anthropic_usage_non_stream_end_to_end` |
| AN-006 | same; streaming default | AC-AN-3, AC-AN-4 | `test_anthropic_usage_stream`, `test_anthropic_usage_stream_last_value_per_field_wins`, `prop_usage_stream_any_chunk_split`, `test_anthropic_usage_stream_end_to_end`, `test_stream_causal_relay_with_usage_tee`, `test_stream_records_usage_field_names_of_message_delta`, `test_stream_metadata_in_summary_log_line`, `test_message_delta_without_split_keeps_cache_split_from_message_start` |
| AN-007 | telemetry never breaks traffic; S2 review X3 | AC-AN-3, AC-AN-6 | `test_usage_parser_failure_is_unavailable`, `test_usage_unavailable_reasons_end_to_end` |
| AN-008 | Claude Code calls count_tokens; Q4 | AC-AN-5 | `test_anthropic_other_endpoints_verbatim` |
| AN-009 | bounded memory; S2 review A3 | AC-AN-4 | `test_usage_parser_memory_bounded`, `test_usage_parser_ignores_large_uninteresting_events_within_bound` |
| AN-010 | a stream cut short still has exact input usage; S2 review A4 | AC-AN-3 | `test_anthropic_usage_stream_with_error_event`, `test_stream_cut_after_message_start_is_partial`, `test_anthropic_usage_stream_with_error_event_end_to_end` |

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
| UP-006 | H34 | AC-UP-4 | `test_logs_never_contain_credentials`, `test_credential_kind_classification`, `test_header_names_only` |
| UP-007 | H37, MD-14 | AC-UP-5 | `test_key_file_with_bom_is_accepted`, `test_utf16_key_file_reported` |
| UP-008 | security hygiene | — | `test_tls_verification_default_on`, `test_tls_custom_ca_bundle_missing_fails` |
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
| PL-007 | Brief§16 redaction seam | AC-PL-3 | `test_new_transformer_needs_no_adapter_change`, `test_new_transformer_through_adapter_end_to_end` |
| PL-008 | Claude Code injects `<system-reminder>` blocks (SPEC 003 rationale) | AC-PL-3 | `test_reminder_spans_protected`, `test_default_stage_list`, `test_pipeline_runs_compression` |

## Token measurement (SPEC 008)

| Req | Why | AC | Tests |
|---|---|---|---|
| TM-001 | H20 | AC-TM-1 | `test_token_counts_stable_fixture` |
| TM-002 | model-dependent tokenizers | AC-TM-1 | `test_tokenizer_selected_by_model_map` |
| TM-003 | Brief§10 exact vs estimate | AC-AN-3 | `test_anthropic_usage_non_stream` (and per protocol) |
| TM-004 | H21; S2 review A1, A2, A6 | AC-TM-5, AC-TM-7 | `test_calibration_factor`, `test_calibration_range_is_inclusive`, `test_calibration_unavailable`, `test_passthrough_request_is_calibrated_with_zero_saving`, `test_whole_request_estimate_excludes_binary_payloads`, `test_whole_request_estimate_counts_every_segment_text`, `test_calibrated_saving_end_to_end`, `test_estimate_off_latency_path`, `test_counter_safe_across_threads` |
| TM-005 | Brief§10 "never present an estimate as exact"; S2 review A7 | AC-TM-4 | `test_every_api_token_field_has_method`, `test_calibrated_saving_end_to_end` |
| TM-006 | MD-02 | AC-TM-2 | `test_missing_tokenizer_fails_with_actionable_message`, `test_tampered_tokenizer_is_reported`, `test_serve_missing_tokenizer_fails_clearly`, `test_load_counter_missing_file`, `test_load_counter_refuses_tampered_file` |
| TM-007 | MD-02, MD-20 | AC-TM-3 | `test_import_has_no_side_effects`, `test_starts_offline_with_provisioned_tokenizer` |
| TM-008 | Brief§19 | AC-TM-1 | `test_fingerprint_equal_across_os`, `test_token_counts_match_reference_values` |
| TM-009 | tokenizer drift detection; S2 review A9 | AC-TM-5 | `test_calibration_outlier_falls_back_to_estimate`, `test_calibration_outlier_end_to_end`, `test_health_degraded_on_calibration_outliers` |
| TM-010 | MD-02; Q7 decision (S0 review P2) | AC-TM-6 | `test_setup_tokenizers_verifies_sha256`, `test_setup_tokenizers_from_file`, `test_setup_tokenizers_refuses_tampered_download`, `test_setup_tokenizers_from_file_rejects_unknown_file`, `test_setup_tokenizers_from_file_never_downloads_missing_ones`, `test_required_tokenizers`, `test_catalog_entries_are_pinned`, `test_check_tokenizer_states`, `test_setup_tokenizers_cli_refuses_unknown_file`, `test_sha256_hex_matches_hashlib` |

## Compression core (SPEC 009)

| Req | Why | AC | Tests |
|---|---|---|---|
| CC-001 | H13 | AC-CC-9 | `test_registry_contract_every_lossless_has_roundtrip_property` |
| CC-002 | S4 SCR-001: enabling is the only gate; the policy is derived | AC-CC-1 | `test_disabled_non_lossless_compressors_never_run`, `test_non_lossless_compressors_run_only_when_enabled`, `test_policy_field_derived_from_enabled_kinds`, `test_policy_forbids_removed_from_closed_set`, `test_ui_lossless_only_shortcut_switches_off_non_lossless` |
| CC-003 | Brief§8 enabled ≠ forced | AC-CC-2 | `test_enabled_compressor_not_applied_when_not_applicable`, `test_disabled_compressor_skipped` |
| CC-004 | Brief§10; tokenizer mismatch margin | AC-CC-3 | `test_longer_output_rejected`, `test_below_min_gain_rejected` |
| CC-005 | Brief§10 invariant | AC-CC-3 | `prop_compression_never_increases_tokens` |
| CC-006 | determinism; H05 | AC-CC-4 | `prop_compression_is_deterministic`, `test_segment_output_independent_of_other_segments` |
| CC-007 | reminders; future redaction markers | AC-CC-5 | `prop_protected_spans_preserved`, `test_protected_span_change_rejected`, `test_transformer_patch_breaking_protected_span_is_dropped`, `test_spans_preserved` |
| CC-008 | H14, MD-25 | AC-CC-6 | `test_compressor_exception_is_recorded`, `test_compressor_timeout_is_recorded`, `test_late_result_discarded_as_timeout` |
| CC-009 | deterministic chains | — | `test_terminal_stops_chain`, `test_chain_order_by_stage_then_id` |
| CC-010 | H14, MD-03 | AC-CC-7 | `test_missing_dependency_marks_compressor_unavailable` |
| CC-011 | Brief§6 | AC-CC-9 | `test_registry_contract_every_lossless_has_roundtrip_property`, `test_json_minify_is_the_only_registered_compressor_in_s1`, `test_registered_compressors_are_available` |
| CC-012 | Brief§11 | AC-CC-8 | `test_compressor_stats_expected_fixture`, `prop_marginal_savings_sum_to_total` |
| CC-013 | Brief§11 skip reasons | AC-CC-8 | `test_compressor_stats_expected_fixture` |
| CC-014 | Brief§9 cheap before expensive; E9; R01§9 (budget = runtime control, provisional default) | AC-CC-8 | `test_budget_exhaustion_skips` |
| CC-015 | H02: lossless is proven by a decoder | AC-CC-9 | `test_registry_contract_every_lossless_has_roundtrip_property`, `test_registry_contract_every_selective_guarantee_has_a_named_test` (S8a-1) |
| CC-016 | defence in depth | AC-CC-9 | `test_verify_lossless_rejects_decode_mismatch` |
| CC-017 | ARCH §5 | AC-CM-7 | `test_import_contracts` |
| CC-018 | superseding rewrites sent history (SPEC 019) | AC-PR-6 | `test_history_rewritten_flag` |
| CC-019 | reference targets keep their content | AC-CC-10 | `test_reference_target_integrity_enforced` |
| CC-020 | R01§2, §7: policy eligibility ≠ default enablement; every transformation relies on model behaviour | AC-CC-11 | `test_every_compressor_declares_assumptions`, `test_registry_default_enabled_requires_eval_record` |
| CC-021 | the bytes stay verbatim in the target | AC-CC-12 | `test_duplicate_pruning_applies_to_verbatim_tools`; S8a SCR-001: `test_verbatim_opt_in_applies_compressor_to_verbatim_tool`, `test_verbatim_opt_in_defaults_off`, `test_verbatim_opt_in_only_for_declaring_compressors`, `test_verbatim_opt_in_does_not_cover_unresolved_tools`, `test_patch_verbatim_opt_in` |
| CC-022 | S1 review P1 (POLICY, provisional) | AC-CC-3 | `test_min_segment_tokens_default` |
| CC-023 | H04; S1 review P2 | AC-CC-12 | `test_unresolved_tool_name_treated_as_verbatim` |
| CC-024 | S1 E9 large-request overhead; S1 Gate 2 decision 2 | AC-CC-13 | `test_result_cache_hit_gives_identical_output`, `test_result_cache_also_caches_not_applicable_and_no_gain`, `test_result_cache_key_includes_view_and_config`, `test_result_cache_still_checks_invariants`, `test_result_cache_bounded`, `test_result_cache_off`, `test_failed_result_is_not_cached`, `test_result_cache_is_safe_under_concurrent_requests` (S4.5, PX-015) |

## Tool-history pruning (SPEC 019)

| Req | Why | AC | Tests |
|---|---|---|---|
| PR-001 | pruners are compressors (ADR 0010) | — | `test_pruning_runs_before_segment_compressors`, `test_duplicate_results_stub_later_copies` |
| PR-002 | repeated tool output | AC-PR-1 | `test_duplicate_results_stub_later_copies`, `test_small_duplicates_not_stubbed`, `test_duplicate_pruning_end_to_end` |
| PR-003 | lossless by reference | AC-PR-1 | `test_duplicate_pruning_never_stubs_first_occurrence`, `prop_duplicate_pruning_decodes_whole_request` |
| PR-004 | provider prefix caching | AC-PR-2 | `test_duplicate_pruning_prefix_stable_across_turns` |
| PR-005 | protocol pairing rules | AC-PR-3 | `test_pruning_preserves_structure_and_arguments` |
| PR-006 | client-specific tool meaning is data, not code | AC-PR-4 | `test_tool_semantics_from_config_only`, `test_unknown_tool_never_superseded`, `test_shell_command_classification_rules`, `test_path_normalisation` |
| PR-007 | E5a: 75 % of pruned entries touched a re-touched file | AC-PR-5 | `test_superseded_read_stubbed_after_full_reread`, `test_edit_never_supersedes`, `test_partial_read_ranges`, `test_superseded_respects_age_and_min_saving` |
| PR-008 | keep the current state visible | AC-PR-4 | `test_unknown_tool_never_superseded`, `test_edit_never_supersedes` |
| PR-009 | cache invalidation visible | AC-PR-6 | `test_history_rewritten_flag` (duplicates never set it) |
| PR-010 | no work on stubbed content | — | `test_pruning_runs_before_segment_compressors` |
| PR-011 | block attributes | — | `test_stub_preserves_cache_control_and_is_error` |
| PR-012 | reference integrity | AC-PR-8 | `test_reference_target_integrity_enforced`, `test_duplicate_stub_names_earliest_copy` |
| PR-013 | verbatim tools | AC-PR-9 | `test_duplicate_pruning_applies_to_verbatim_tools` |
| PR-015 | Claude Code reminders inside results; ambiguous multi-block results (S4 review P6, P7, A5) | — | `test_duplicate_stub_keeps_protected_spans`, `test_multi_block_results_not_pruned`, `test_reference_stubs_counted`, `test_duplicate_require_same_call_option`, `test_pruner_records_why_it_did_not_stub` |
| PR-014 | shell-command classification defined in the spec; Codex Windows/Unix shapes (MD-13) | AC-PR-10 | `test_shell_command_classification_rules` |

## Compressors (SPEC 010)

| Req | Why | AC (in spec) | Tests |
|---|---|---|---|
| CP-JM-001 | pretty-printed JSON is common in tool output; expected range in TOKLI_EVIDENCE §2 | json_minify tests | `prop_json_minify_decode_roundtrip`, `test_json_minify_basic`, `test_json_minify_applied_through_engine` |
| CP-JM-002 | H09 | " | `test_json_minify_preserves_number_spelling`, `test_json_minify_preserves_duplicate_keys`, `test_json_minify_preserves_escapes_and_unicode` |
| CP-JM-003 | pass-through preference | " | `test_json_minify_not_applicable_on_mixed_text`, `test_json_minify_rejects_nan`, `test_json_minify_not_applicable_without_whitespace` |
| CP-JM-004 | H04 | " | `test_json_minify_skipped_for_verbatim_tool` |
| CP-JM-005 | correctness constraint: linear time (R01§9) | " | `test_json_minify_linear_time` |
| CP-SG-001 | grep output repeats the path on every match line | search_group tests | `prop_search_group_decode_roundtrip`, `test_search_group_groups_consecutive_same_path`, `test_search_group_min_group_lines_counts_whole_segment` (review A8), `test_search_group_no_group_reason`, `test_search_group_ignores_non_grep_lines`, `test_search_group_linear_time` |
| CP-SG-002 | H02, H03 | " | `test_search_group_keeps_unparsed_lines_in_place` |
| CP-SG-003 | H03, MD-11 | " | `test_search_group_windows_paths_roundtrip`, `test_search_group_ignores_timestamps`, `test_search_group_ignores_non_grep_lines` (S8a SCR-003) |
| CP-SG-004 | MD-12 | " | `test_search_group_crlf_roundtrip`, `test_search_group_mixed_line_endings_roundtrip`, `test_search_group_escaping`, `prop_search_group_decode_roundtrip` |
| CP-DI-001 | dictionary evidence in TOKLI_EVIDENCE §2; algorithm fully specified (R01§B) | dictionary tests | `prop_dictionary_decode_roundtrip`, `test_dictionary_selection_deterministic_tie_break`, `test_dictionary_nested_symbol_decode_order`, `test_dictionary_no_gain_not_applied` |
| CP-DI-002 | symbols colliding with input text would make decoding ambiguous | " | `test_dictionary_collision_guard` |
| CP-DI-003 | lossless by decoder | " | `prop_dictionary_decode_roundtrip` |
| CP-DI-004 | substitution inside protected spans, URLs or quoted strings corrupts them | " | `test_dictionary_does_not_touch_urls_or_protected_spans` |
| CP-DT-001 | retention contract of the selective diff trim | diff tests | `test_diff_trim_preserves_changed_lines`, `test_diff_trim_preserves_headers` |
| CP-DT-002 | H10 | " | `test_diff_trim_does_not_swallow_trailing_text` |
| CP-DT-003 | honesty to the model | " | `test_diff_trim_omission_note` |
| CP-DT-004 | H11 | " | `test_diff_trim_false_positive_shapes` |
| CP-LF-001 | retention contract of the selective log filter | log tests | `test_log_filter_keeps_error_and_warn`, `test_log_filter_keeps_unleveled_lines`, `test_log_filter_order_preserved` |
| CP-LF-002 | safety gate | " | `test_log_filter_gate`, `test_log_filter_keywords_are_whole_words`, `test_log_filter_keywords_case_insensitive` |
| CP-LF-003 | honesty to the model | " | `test_log_filter_omission_note`, `test_log_filter_note_line_endings` (review A6), `test_log_filter_nothing_omitted_reason` |
| CP-LF-004 | selection rules defined in Tokli terms (R01§B) | " | `test_log_filter_normalisation_and_sampling`, `test_log_filter_mixed_keywords_kept_as_severe`, `test_log_filter_most_verbose_routine_level_wins`, `test_log_filter_linear_time` |

## Routing (SPEC 011)

| Req | Why | AC | Tests |
|---|---|---|---|
| RT-001 | cheap structural features; H11 (S1: `tokens`, `json_candidate`; `test_grep_feature_windows_paths` arrives with `search_group`, S8) | AC-RT-1 | `test_features_linear_time`, `test_grep_feature_windows_paths`, `test_leveled_ratio_feature`, `test_line_count_and_crlf_features` (S8a-1), `test_grep_feature_ignores_timestamps` (S8a SCR-003) |
| RT-002 | Brief§9 cheap first | AC-RT-2 | `test_cheap_filters_before_applicable` |
| RT-003 | Brief§9 prefer pass-through | AC-RT-3 | `test_prose_only_request_passthrough` |
| RT-004 | Brief§9 | AC-RT-2 | `test_cheap_filters_before_applicable` |
| RT-005 | H12 | AC-RT-4 | `test_routing_inputs_closed_and_no_ml` |
| RT-006 | Brief§14 "why" | AC-RT-2 | `test_trace_shows_routing_counts` |

## Quality evaluation (SPEC 012)

| Req | Why | AC | Tests |
|---|---|---|---|
| QE-001 | H23: harnesses that bypass the real pipeline | AC-QE-3 | `test_harness_uses_real_pipeline`, `test_smoke_arms_differ_only_in_candidate` |
| QE-002 | Brief§21 | AC-QE-3 | `test_harness_report_provenance` |
| QE-003 | H23: one case per category | AC-QE-1 | `test_harness_insufficient_data` |
| QE-004 | H23: metrics that normalise away removed content | AC-QE-2 | `test_checker_exact_value`, `test_checker_json_structural`, `test_checker_registry_is_closed`, `test_smoke_harness_self_test` (S2.5); `test_harness_detects_destructive_compressor` (S8) |
| QE-005 | reproducibility | AC-QE-3 | `test_harness_report_provenance` |
| QE-006 | default-enable gate | release checklist | (process) + `test_registry_default_enabled_requires_eval_record` |
| QE-007 | H23: constant or fabricated scores | AC-QE-1 | `test_smoke_insufficient_data`, `test_eval_stops_at_call_cap` (S2.5); `test_harness_insufficient_data` (S8) |
| QE-008 | marginal vs isolated (TELEMETRY §2) | AC-QE-3 | `test_harness_identity_ci_contains_zero` (+ isolated/chained report fields) |
| QE-009 | Q11 decision: eval budget belongs to the user | AC-QE-4, AC-QE-8 | `test_eval_requires_confirmation_or_yes` (S2.5, via QE-018); `test_eval_requires_confirmation_or_max_cost` (S6) |
| QE-010 | same; no surprise spend | AC-QE-4 | `test_eval_stops_at_call_cap` (S2.5); `test_eval_stops_at_cost_cap` (S6) |
| QE-011 | same; never automatic | AC-QE-4 | `test_eval_never_auto_starts`, `test_eval_requires_max_calls_without_pricing`, import contract `tokli.http \| tokli.eval` |
| QE-012 | R01§8: behaviour-dependent defaults arrive in S4, before the S8 harness; S2.5 review A1–A3 | AC-QE-5 | `test_smoke_arms_differ_only_in_candidate`, `test_harness_uses_real_pipeline`, `test_case_not_exercised_is_excluded`, `test_cases_load_by_assumption`, `test_eval_temperature_default_omits_the_parameter`, `test_eval_temperature_zero_by_default` (S2.5 SCR-001) |
| QE-013 | R01§8: one case format for smoke and full tiers; test-data hygiene | AC-QE-6 | `test_eval_cases_lint`, `test_s8a1_families_exist`, `test_s8a1_cases_exercise_their_compressor` (S8a-1), `test_s8a1_cases_do_not_exercise_the_other_compressor` (S8a SCR-003) |
| QE-014 | R01§8 deterministic recording of configuration, saving and outcome | AC-QE-3 | `test_harness_report_provenance` |
| QE-015 | R01§8: explicit, honest verdict rule | AC-QE-5 | `test_smoke_verdict_rule`, `test_smoke_insufficient_data`, `test_unexercised_family_does_not_enter_verdict`, `test_assumption_without_exercised_family_is_insufficient` (S8a SCR-002) |
| QE-016 | R01§7: CC-020 needs a machine-readable record | AC-QE-7 | `test_eval_record_schema_and_provisional_rule`, `test_eval_record_invalidated_by_version_bump`, `test_harness_report_provenance`, `test_registry_default_enabled_requires_eval_record` |
| QE-017 | the harness must prove it can detect damage | AC-QE-2 | `test_smoke_harness_self_test`, `test_smoke_harness_self_test_reference_families`, `test_reference_families_exist_for_the_pruner` |
| QE-018 | no price book before S6; S2.5 review X1, P2 | AC-QE-8 | `test_eval_requires_max_calls_without_pricing`, `test_eval_requires_confirmation_or_yes`, `test_eval_stops_at_call_cap` |
| QE-019 | the proxy never holds credentials; S2.5 review X2, P3; ADR 0008 | AC-QE-8 | `test_eval_api_key_from_named_env_only`, `test_eval_never_writes_the_key`, `test_eval_sends_key_only_as_header` |
| QE-020 | H23: checkers that cannot hide removed content; S2.5 review A5; S4 P9 | AC-QE-8 | `test_checker_exact_value`, `test_checker_json_structural`, `test_checker_verbatim_line` |

## Telemetry & cost (SPEC 013)

| Req | Why | AC | Tests |
|---|---|---|---|
| TC-001 | Brief§11/§14 | AC-TC-1 | `test_request_record_persisted_per_outcome`, `test_records_round_trip`, `test_telemetry_db_created_in_data_dir` |
| TC-002 | Brief§11 | AC-TC-1 | `test_compressor_stats_only_for_considered` |
| TC-003 | Brief§11 attribution | AC-TC-2 | `prop_marginal_savings_sum_to_total` |
| TC-004 | Brief§12; H05, H22 | AC-TC-3 | `test_cost_proportional_estimate_and_bounds` |
| TC-005 | Brief§12 "never fabricate" | AC-TC-4 | `test_cost_unavailable_without_price` |
| TC-006 | honest fallback | AC-TC-3 | `test_cost_assumes_uncached_without_usage` |
| TC-007 | Brief§12 claim only affected categories | AC-TC-3 | `test_no_output_savings_claimed` |
| TC-008 | H22 | AC-TC-5 | `test_price_effective_dates` |
| TC-009 | Brief§12 pricing ≠ compression | AC-CM-7 | `test_import_contracts` |
| TC-010 | Brief§15 retention | AC-TC-1 | `test_retention_pruning`, `test_retention_zero_keeps_everything` |
| TC-011 | telemetry must not break traffic | AC-TC-6 | `test_sink_failure_degrades_not_breaks`, `test_write_failure_counts_and_never_raises`, `test_close_never_closes_the_connection_under_a_busy_writer` (S4.5) |
| TC-012 | additive migrations keep older data readable; ADR 0005 | AC-TC-1, AC-TC-9 | `test_schema_migration_forward`, `test_schema_migration_forward_from_v1` (v1 → v3), `test_schema_version_recorded`, `test_non_ascii_data_dir`, `test_usage_and_calibration_fields_round_trip`; S4.5 D2: `test_column_type_follows_field_annotation`, `test_unmapped_annotation_is_refused`, `test_existing_column_types_unchanged` |
| TC-013 | R01§9: measure overhead from the first useful slice; target ≠ gate | AC-TC-7 | `test_overhead_percentiles_by_bucket`, `test_target_is_reference_not_status`, `test_unknown_size_bucket`, `test_overhead_groups_by_policy_and_config_hash`, `test_ui_overhead_target_is_reference_line` |
| TC-014 | PR-009 flag was not in the record schema (R01§10 consistency pass) | AC-TC-8 | `test_request_record_pruning_fields` |
| TC-015 | honest totals (H21); S3 review A1–A4, P4 | AC-TC-11 | `test_summary_totals_hand_computed`, `test_summary_labels_mixed_totals_as_estimate_with_share`, `test_requests_list_metadata_only` |
| TC-016 | which compressor saves, at what latency (TOKLI_TELEMETRY_AND_COST §3); ADR 0007 | AC-TC-12 | `test_compressor_aggregates_hand_computed`, `test_compressor_rates_without_applicable_are_null`, `test_latency_without_benefit_flag`, `test_stats_record_tokens_in_of_accepted_calls` |

## Observability (SPEC 014)

| Req | Why | AC | Tests |
|---|---|---|---|
| OB-001 | Brief§14 | AC-OB-1 | `test_request_id_propagates_everywhere`, `test_request_ids_are_ulids_and_sortable` |
| OB-002 | Brief§14 timings | AC-OB-2 | `test_trace_contains_all_spans`, `test_trace_to_dict` |
| OB-003 | "diagnose without a debugger" | AC-OB-3 | `test_trace_buffer_bounded` |
| OB-004 | Brief§14 decisions | AC-RT-2 | `test_reason_codes_closed_set`, `test_reason_codes_known` |
| OB-005 | provider support cases | AC-OB-1 | `test_upstream_correlation_ids_recorded` |
| OB-006 | H31 | AC-OB-4 | `test_upstream_error_logging_respects_content_rule` |
| OB-007 | H34 | AC-OB-4 | `test_logs_never_contain_credentials`, `test_redaction_masks_credentials`, `test_json_log_line_is_structured_and_redacted` |
| OB-008 | Brief§15 | AC-OB-4 | `test_default_logging_contains_no_prompt_text` |
| OB-009 | Brief§15 explicit, visible debug | AC-OB-5 | `test_debug_content_requires_both_switches`, `test_debug_content_banner_visible`, `test_debug_content_ttl_and_cap` |
| OB-010 | ops | AC-OB-1 | `test_request_summary_log_line` |
| OB-011 | degraded visibility; S2 review A8 | AC-TC-6 | `test_health_degraded_conditions`, `test_health_endpoint`, `test_outlier_window`, `test_health_degraded_on_calibration_outliers` |
| OB-012 | E1 needs the header names Claude Code sends; S1 review P6; S1 Gate 2 decision 3 | AC-OB-4, AC-OB-6 | `test_trace_records_header_names_only`, `test_header_names_persisted`, `test_header_names_persisted_end_to_end` |
| OB-013 | logs outlive the console; S1 Gate 2 decision 4 | AC-OB-7 | `test_log_file_defaults`, `test_log_file_written_when_enabled`, `test_log_file_rotates`, `test_log_file_rotation_failure_does_not_stop_tokli`, `test_log_file_rotation_with_file_held_open`, `test_log_file_open_failure_does_not_stop_tokli`, `test_log_file_contains_no_credentials_or_content`, `test_serve_log_file_enabled`, `test_serve_log_file_off_by_default` |

## Application API (SPEC 015)

| Req | Why | AC | Tests |
|---|---|---|---|
| API-001 | Brief§13 no content | AC-API-2 | `test_api_returns_no_content_or_credentials`, `test_api_returns_no_content_or_credentials_s3`, `test_requests_list_metadata_only`, `test_trace_served_from_db_after_buffer_eviction` |
| API-002 | Brief§10/§12 labelling | AC-API-1 | `test_every_api_token_field_has_method`, `test_every_api_token_field_has_method_s3`, `test_api_contract_schemas`, `test_api_contract_schemas_s3` |
| API-003 | Brief§13 breakdowns | AC-API-1 | `test_metrics_filters_validated`, `test_metrics_filters_validated_over_http`, `test_filters_default_to_last_seven_days` |
| API-004 | replaceable UI (Brief§4) | AC-API-1 | `test_api_contract_schemas`, `test_api_contract_schemas_s3` |
| API-005 | config ownership | AC-API-3 | `test_patch_pinned_key_conflict`, `test_patch_unknown_key_rejected`, `test_patch_rejects_malformed_body` |
| API-006 | browser-origin mutations | AC-API-4 | `test_mutation_rejects_foreign_origin` |
| API-007 | atomic, persisted changes; ADR 0009 | AC-API-5 | `test_config_change_atomic_snapshot`, `test_patch_persists_to_ui_overrides_file`, `test_patch_noop_returns_same_hash`, `test_ui_toggle_changes_next_config_hash_and_attribution`, `test_config_reload_reads_new_overrides`; S4.5 D1: `test_concurrent_patches_keep_every_change`, `test_failed_write_leaves_no_temporary_file` |
| API-008 | UI ↛ internals; ADR 0006 | AC-CM-7 | `test_import_contracts` (contract "API routes reach storage only through tokli.app use cases") |
| API-009 | DNS rebinding; S3 review M4, P7 | AC-API-6 | `test_tokli_routes_reject_foreign_host`, `test_proxy_routes_ignore_host_check` |
| API-010 | S3 review A5, A6 | AC-API-7 | `test_summary_compressor_filter`, `test_timeseries_hour_and_day_buckets`, `test_timeseries_buckets_follow_tz_across_dst`, `test_metrics_filters_validated` |
| API-011 | S3 review M2 | — | `test_summary_empty_database`, `test_summary_missing_database_file`, `test_metrics_telemetry_disabled`, `test_metrics_query_failure_isolated` |
| API-012 | S3 review X1, P6 | — | `test_summary_cost_block_null_until_s6`, `test_ui_money_shows_dash_with_reason` |

## Dashboard (SPEC 016)

| Req | Why | AC | Tests |
|---|---|---|---|
| UI-001 | Brief§8, §13 | AC-UI-1 | `test_ui_has_no_compressor_specific_code` |
| UI-002 | Brief§10/§12 | AC-UI-2 | `test_ui_renders_method_labels`, `test_ui_money_shows_dash_with_reason` |
| UI-003 | Brief§8 kind visibility; R01§3 equivalence and assumptions visible | AC-UI-2 | `test_ui_shows_kind_equivalence_and_assumptions`, `test_ui_shows_equivalence_assumptions_and_eval_status`, `test_compressors_endpoint_shows_locks_and_evaluation`, `test_current_record`, `test_outdated_record_shown_as_outdated`, `test_wheel_contains_eval_records` |
| UI-004 | S4 SCR-001: toggles plus the Lossless only shortcut | AC-UI-3 | `test_ui_lossless_only_shortcut_switches_off_non_lossless`, `test_ui_toggle_patches_config` |
| UI-005 | config ownership | AC-UI-3 | `test_ui_locked_settings_show_source` |
| UI-006 | H41, MD-21 | AC-UI-4 | `test_wheel_contains_ui_assets`, `test_ui_assets_load_offline`, `test_ui_assets_load_offline_in_browser` |
| UI-007 | Brief§15 | AC-OB-5 | `test_debug_content_banner_visible` |
| UI-008 | usability | AC-UI-2 | `test_ui_usable_at_360px` |
| UI-009 | R01§9: expensive compressors visible and controllable | AC-UI-2 | `test_ui_overhead_target_is_reference_line`, `test_compressor_aggregates_hand_computed` (cost class, average latency, budget-skip rate, `budget_ms`) |
| UI-011 | S3 review M3, P8; Windows file-type registry | AC-UI-5 | `test_dashboard_served_at_tokli_root`, `test_ui_assets_served_with_explicit_content_types`, `test_serve_prints_dashboard_address` |
| UI-012 | the verbatim opt-in is the user's informed choice (S8a SCR-001, E5b-lite) | — | `test_ui_verbatim_opt_in_toggle` |
| UI-010 | honest wording (S4 SCR-001) | — | `test_ui_policy_explanations_text` |

## Configuration (SPEC 017)

| Req | Why | AC | Tests |
|---|---|---|---|
| CF-001 | MD-05 | AC-CF-1 | `test_env_overrides_file_for_every_key`, `test_cli_overrides_env`, `test_ui_override_only_when_not_pinned`, `test_set_flag_overrides_env`, `test_defaults_when_no_layers`, `test_config_file_found_in_config_dir`, `test_named_flag_source`, `test_nested_keys_and_env_names` |
| CF-002 | Brief§18 inspectable | AC-CF-1 | `test_config_show_reports_sources` |
| CF-003 | fail clearly (Brief§18) | AC-CF-2 | `test_keys_added_in_s2_defaults`, `test_keys_added_in_s2_reject_out_of_range`, `test_unknown_key_rejected_with_layer`, `test_unknown_section_rejected`, `test_invalid_value_names_layer_key_and_expected_type`, `test_explicit_config_file_must_exist`, `test_set_requires_key_equals_value` |
| CF-004 | MD-04, MD-08 | AC-CF-3 | `test_cwd_config_and_dotenv_ignored` |
| CF-005 | mid-request consistency | AC-API-5 | `test_config_snapshot_immutable` |
| CF-006 | fingerprint + telemetry; S4 SCR-002 (`pruning`) | AC-CF-4 | `test_config_hash_stable_and_sensitive`, `test_config_hash_changes_with_pruning_options`, `test_ui_override_changes_config_hash` |
| CF-007 | H12, H14: no silent substitution | AC-CC-7 | `test_optional_capability_never_silently_substituted` |
| CF-008 | MD-04, MD-07 | AC-PT-2 | `test_data_dir_resolution_per_platform`, `test_config_dir_resolution_per_platform`, `test_linux_xdg_fallbacks_use_home`, `test_missing_home_fails_clearly` |
| CF-009 | Brief§8 UI; S4 SCR-001 | AC-API-3 | `test_keys_marked_ui_editable`, `test_patch_unknown_key_rejected`, `test_s8a1_keys_and_defaults`, `test_patch_verbatim_opt_in` (S8a SCR-001) |
| CF-010 | credential hygiene | AC-CF-5 | `test_secret_values_rejected_in_config` |
| CF-011 | MD-05; S0 review M2, X2 | AC-CF-6 | `test_env_json_value_errors_name_variable`, `test_reserved_env_vars_only` |
| CF-012 | S0 review M1 (YAML implicit types, duplicate keys) | AC-CF-7 | `test_duplicate_yaml_key_rejected`, `test_yaml_implicit_types_rejected`, `test_empty_config_file_is_an_empty_layer` |

## Portability & diagnostics (SPEC 018)

| Req | Why | AC | Tests |
|---|---|---|---|
| PT-001 | Brief§19 | AC-PT-1 | `test_fingerprint_equal_across_os` |
| PT-002 | Brief§24 example; MD-04…MD-08 | AC-PT-1 | `test_behaviour_independent_of_cwd`, `test_temp_home_clean_start`, `test_hostile_environment_ignored`, `test_serve_process_end_to_end` |
| PT-003 | MD-02, MD-24 | AC-PT-3 | `test_no_outbound_connections_except_upstream` |
| PT-004 | MD-18 | AC-PT-1 | CI matrix + `test_doctor_reports_python_version` |
| PT-005 | Brief§20 | AC-PT-2 | `test_doctor_report_fields` |
| PT-006 | Brief§20 "explain differences" | AC-PT-5 | `test_fingerprint_explain_config_difference`, `test_fingerprint_explain_tokenizer_difference` |
| PT-007 | Brief§20 never expose secrets | AC-PT-2 | `test_doctor_never_prints_secrets` |
| PT-008 | fail clearly | AC-PT-4 | `test_port_in_use_fails_clearly`, `test_unwritable_data_dir_fails_clearly`, `test_missing_tokenizer_fails_with_actionable_message`, `test_alternative_port`, `test_serve_port_in_use_fails_clearly` |
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
