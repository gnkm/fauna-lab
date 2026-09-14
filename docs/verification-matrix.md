# 検証対応表（SRS 4 章）

機能 ID F018。SRS-FAUNALAB-002 版 2.2 の `VER-*` から試験へ辿る表である。

## 辿り方

1. 本表の **試験** 列（モジュール / 関数名）
2. pytest マーカー: `uv run --directory backend pytest -m ver_obs_001` のように `VER-*` を小文字・ハイフンをアンダースコアにした名前
3. 試験関数名・ docstring の `VER-...` 文字列

単一の自動試験コマンドは `pnpm test`（内部は `uv run --directory backend pytest`、カバレッジ付き）。外部ネットワークに依存しない。Playwright は `pnpm test:e2e`（セットアップでブラウザ取得。実行時ネット不要）。

方法の記号: `pytest` = 単一コマンドに含む。`playwright` = UI 受入。`inspect` = 成果物・設定の静的確認（pytest 内）。`manual` = 自動試験にしない。

| VER ID | 方法 | 試験 | 未実装・制限の理由 |
| --- | --- | --- | --- |
| `VER-OBS-001` | pytest | `test_state.py`（`test_state_has_required_keys` / `test_consecutive_gets_are_equal_except_observed_at`）。UI 反映は Playwright | Web UI 全操作後の確認は 9.2 の経路で部分的 |
| `VER-API-001` | pytest | `test_ver_api.py` / `test_openapi_contract.py` / `test_state.py::test_unhandled_exception_returns_problem_and_keeps_process` | OpenAPI 全操作の網羅呼び出しは F019。本表はパス集合の一致・7 類ステータス・本文漏洩 |
| `VER-UI-001` | playwright | `e2e/overview.spec.ts` / `e2e/images-annotate-splits.spec.ts` / `e2e/train-models-infer.spec.ts` | 全 REQ-UI の網羅ではなく、全画面 URL 直達・リロードと主経路 |
| `VER-COM-001` | manual | 提出時。補助: `test_ver_con.py::test_ver_con_001_compose_blocks_runtime_pull` | ホスト NIC 切断の完全エアギャップは Cloud Agent / CI で再現しない（DESIGN I-NET-001） |
| `VER-F-IMG-001` | pytest | `test_images.py::test_ver_f_img_001_jpeg_png_fake_and_oversize` | |
| `VER-F-IMG-002` | pytest | `test_images.py::test_ver_f_img_002_partial_success_and_duplicate` | |
| `VER-F-IMG-003` | pytest | `test_images.py::test_ver_f_img_003_survives_restart` | |
| `VER-F-IMG-004` | pytest | `test_images.py::test_ver_f_img_004_filter_and_pagination` | |
| `VER-F-IMG-005` | pytest | `test_images.py::test_ver_f_img_005_delete_cascade_and_path_traversal` | |
| `VER-F-ANN-001` | pytest | `test_labels.py::test_ver_f_ann_001_overwrite_and_bulk_missing_is_atomic` | |
| `VER-F-DS-001` | pytest | `test_splits.py::test_ver_f_ds_001_stratified_within_one` | |
| `VER-F-DS-002` | pytest | `test_splits.py::test_ver_f_ds_002_same_seed_matches` | |
| `VER-F-TRN-001` | pytest | `test_jobs.py::test_ver_f_trn_001_start_returns_within_one_second` | |
| `VER-F-TRN-002` | pytest | `test_jobs.py::test_ver_f_trn_002_precondition_and_single_running` | |
| `VER-F-TRN-003` | pytest | `test_jobs.py::test_ver_f_trn_003_transitions_and_cancel` | |
| `VER-F-TRN-004` | pytest | `test_jobs.py::test_ver_f_trn_004_epoch_progress_and_logs` | 自動試験は短縮エポック |
| `VER-F-TRN-005` | pytest | `test_jobs.py::test_ver_f_trn_005_baseline_paths_and_thirty_images` | |
| `VER-F-TRN-006` | pytest | `test_jobs.py::test_ver_f_trn_006_reproducible_test_accuracy` | |
| `VER-F-TRN-007` | pytest | `test_jobs.py::test_ver_f_trn_007_restart_fails_running` | 強制終了は DB に残した RUNNING と再起動で代替 |
| `VER-F-MDL-001` | pytest | `test_metrics.py::test_ver_f_mdl_001_matrix_identity` / `test_models.py` 再評価 | |
| `VER-F-MDL-002` | pytest | `test_models.py::test_ver_f_mdl_002_version_zero_active_delete_refused_restart` / `test_jobs.py::test_ver_f_mdl_002_first_trained_activates_second_does_not` | |
| `VER-F-INF-001` | pytest | `test_inferences.py::test_ver_f_inf_001_fails_without_active_model` | |
| `VER-F-INF-002` | pytest | `test_inferences.py::test_ver_f_inf_002_model_ref_frozen_and_score_sum` | |
| `VER-F-BASE-001` | pytest | `test_inferences.py::test_ver_f_base_001_http_inferences_match_expectations` / `test_baseline_expectations.py` | |
| `VER-F-BASE-002` | pytest | `test_inferences.py::test_ver_f_base_002_scores_other_mass_unmapped_low_conf` | |
| `VER-F-BASE-003` | pytest | `test_baseline.py::test_ver_f_base_003_five_startup_states` | |
| `VER-F-BASE-004` | pytest | `test_inferences.py::test_ver_f_base_004_class_map_swap_changes_inference` | 改変はコピー上。リポジトリ `assets/` は読み取り専用 |
| `VER-F-SUG-001` | pytest | `test_suggestions.py::test_ver_f_sug_001_generate_skips_labeled_and_needs_model` | |
| `VER-F-SUG-002` | pytest | `test_suggestions.py::test_ver_f_sug_002_label_clears_and_regenerate_overwrites` | |
| `VER-F-SUG-003` | pytest | `test_suggestions.py::test_ver_f_sug_003_threshold_accept_sets_model_suggested` | |
| `VER-F-SUG-004` | pytest | `test_suggestions.py::test_ver_f_sug_004_suggestions_are_not_confirmed_labels` | |
| `VER-F-SYS-001` | pytest | `test_state.py::test_empty_data_dir_registers_eight_classes` / `test_sample.py::test_ver_f_sys_001_sample_import_registers_labels` | |
| `VER-USE-001` | manual | README / UI 空状態の案内 | 被験者 15 分は自動試験に載せない |
| `VER-USE-002` | playwright | `e2e/images-annotate-splits.spec.ts`（削除確認）。空状態は `e2e/overview.spec.ts` | 全画面の目視確認は初期対象外 |
| `VER-USE-003` | manual | — | 推奨（S）。キーボードとコントラストの自動計測は初期必須から外す |
| `VER-PERF-001` | manual | — | 基準環境（4 論理 CPU・8 GB）・画像 1000 が Cloud Agent で再現できない |
| `VER-PERF-002` | manual | — | 同上 |
| `VER-PERF-003` | manual | — | 同上 |
| `VER-DATA-001` | pytest | `test_state.py::test_classes_match_srs_352` | |
| `VER-DATA-002` | pytest | `test_ver_data.py::test_ver_data_002_invariants_hold_after_operations` | |
| `VER-DATA-003` | pytest | `test_ver_data.py::test_ver_data_003_writes_stay_in_data_dir` | |
| `VER-DATA-004` | pytest | `test_models.py::test_ver_data_004_baseline_reeval_matches_annex` | |
| `VER-CON-001` | inspect / manual | `test_ver_con.py::test_ver_con_001_compose_blocks_runtime_pull` | 実 NIC 遮断起動は提出時。Compose の masquerade 無効と `pull_policy: never` で代替 |
| `VER-CON-002` | pytest | `test_licenses.py` / `test_web_licenses.py` / `test_ver_con.py::test_ver_con_002_settings_from_environment` / `test_jobs.py::test_chance_level_beaten_on_baseline_head` | 偶然水準は短縮エポックのベースラインヘッド経路 |
| `VER-ATT-001` | pytest | `test_ver_att.py::test_ver_att_001_malformed_requests_keep_process` / `test_state.py` 未処理例外 | |
| `VER-ATT-002` | pytest / playwright | `test_ver_att.py::test_ver_att_002_special_names_stay_values` / `test_images.py` パス横断 / `e2e/images-annotate-splits.spec.ts` HTML | |
| `VER-ATT-003` | pytest | `test_ver_att.py::test_ver_att_003_readme_lint_and_single_command`。カバレッジ 70 % は `pyproject.toml` の `fail_under` | Playwright は単一コマンドに含めない（ブラウザ取得がセットアップ） |
| `VER-ATT-004` | pytest | `test_ver_att.py::test_ver_att_004_copied_data_dir_restores_state` | 縮小データ。別ホストへの提出時コピー手順は ARCHITECTURE 6.4 |
