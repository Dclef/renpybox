from module.Localizer.LocalizerZH import LocalizerZH

_PACK_UNPACK_ERROR_EN = {
    "UNSAFE_PATH": "The RPA archive contains unsafe paths. Unpacking was refused.",
    "UNSAFE_INDEX": "The RPA archive index could not be read safely; unpacking was refused.",
    "VALIDATION_FAILED": "RPA archive path validation failed.",
    "NO_GAME_PYTHON": "The game's bundled Python runtime was not found.",
    "MISSING_RESOURCE": "A required unpacking resource is missing.",
    "INVALID_DIR": "The game folder does not exist or is invalid.",
    "EXTRACTOR_FAILED": "The game's Ren'Py unpacker exited with an error.",
    "UNAVAILABLE": "No unpackable RPA files were found, or every unpacking method failed.",
    "UNREN_SKIPPED": "Direct and external unpacking both failed, and the UnRen fallback is disabled because the archives could not be validated safely.",
}


class LocalizerEN(LocalizerZH):

    # 保留
    switch_language: str = (
        "请选择应用语言，新的语言设置将在下次启动时生效 …"
        "\n"
        "Select application language, changes will take effect on restart …"
    )
    switch_language_toast: str = (
        "应用语言切换成功，请重启应用生效 …"
        "\n"
        "Language switched successfully, please restart the application for changes to take effect …"
    )

    # 通用
    add: str = "Add"
    edit: str = "Edit"
    none: str = "None"
    back: str = "Back"
    next: str = "Next"
    stop: str = "Stop"
    start: str = "Start"
    timer: str = "Timer"
    close: str = "Close"
    alert: str = "Alert"
    warning: str = "Warning"
    confirm: str = "Confirm"
    cancel: str = "Cancel"
    later: str = "Later"
    auto: str = "Auto"
    wiki: str = "Wiki"
    open: str = "Open"
    select: str = "Select"
    inject: str = "Inject"
    filter: str = "Filter"
    search: str = "Search"
    generate: str = "Generate"
    placeholder: str = "Please enter keywords …"
    task_success: str = "Task succeeded …"
    alert_no_data: str = "No valid data …"
    alert_reset_timer: str = "Confirm to reset timer?"
    alert_reset_translation: str = "Confirm to reset translation task and start a new task?"
    search_prev: str = "Previous"
    search_next: str = "Next"
    search_prev_match: str = "Previous match"
    search_next_match: str = "Next match"
    search_regex_on: str = "Regex Mode\nCurrent Status: Enabled"
    search_regex_off: str = "Regex Mode\nCurrent Status: Disabled"
    search_regex_invalid: str = "Invalid regular expression"
    search_no_match: str = "No matches found"
    search_regex_btn: str = "Regex"
    search_match_info: str = "Item {current} of {total}"
    search_no_result: str = "No results"
    current_status: str = "Current Status: "

    # 主页面
    app_close_message_box: str = "Are you sure you want to exit the application … ?"
    app_new_version: str = " Update available"
    app_new_version_toast: str = "New version available: {VERSION}"
    app_new_version_update: str = " Downloading {PERCENT}"
    app_new_version_failure: str = "Update download failed: "
    app_new_version_success: str = "Update downloaded"
    app_new_version_downloaded: str = " Ready to install"
    app_new_version_waiting_restart: str = "Restarting to install update"
    app_new_version_apply_failure: str = "Failed to apply update: "
    app_theme_btn: str = "Switch Theme"
    app_brand_short: str = "RB"
    app_brand_name: str = "RenpyBox"
    app_titlebar_project: str = "Project: {NAME}"
    app_titlebar_project_unset: str = "No project selected"
    app_language_btn: str = "Language"
    app_settings_page: str = "App Settings"
    app_platform_page: str = "API"
    app_project_page: str = "Project Settings"
    app_renpy_toolbox_page: str = "Ren'Py Toolbox"
    app_workbench_page: str = "Character / Worldbook Workbench"
    app_translation_page: str = "Translation Task"
    app_agent_page: str = "Agent Assistant"
    app_proofreading_page: str = "Proofreading"
    translation_page_header_title: str = "Task Monitor"
    translation_page_header_description: str = "Track translation progress, throughput, and recovery actions"
    translation_page_header_summary: str = "Current task · {SOURCE} ➔ {TARGET} · Worker pool {RUNNING}/{MAX}"
    translation_page_progress_title: str = "Overall Translation Progress"
    translation_page_progress_empty: str = "0.0%\n0 / 0"
    translation_page_throughput_title: str = "Real-time Token Throughput"
    translation_page_peak_speed: str = "Peak {SPEED} T/s"
    translation_page_kpi_progress: str = "Translation Progress"
    translation_page_kpi_throughput: str = "Live Throughput"
    translation_page_lines_detail: str = "{LINE:,} / {TOTAL:,} lines"
    translation_page_trend_live: str = "Live"
    translation_page_trend_idle: str = "Idle"
    translation_page_trend_total: str = "Total"
    translation_page_trend_healthy: str = "Healthy"
    translation_page_translated_percent: str = "Translated {PERCENT:.1f}%"
    translation_page_pending_percent: str = "Pending {PERCENT:.1f}%"
    translation_page_cache_percent: str = "Cached {PERCENT:.1f}%"
    translation_page_cache_unavailable: str = "Cached —"
    translation_page_stat_average: str = "Average"
    translation_page_stat_batches: str = "Batches"
    translation_page_stat_cache_hit: str = "Cache hit"
    translation_page_stat_latency: str = "Latency"
    translation_page_open_proofreading: str = "Open Parallel Proofreading"
    translation_page_export_snapshot: str = "Export Snapshot"
    translation_page_elapsed: str = "Elapsed: {TIME}"
    translation_page_remaining: str = "Remaining: {TIME}"
    translation_page_duration_hms: str = "{H}h {M}m {S}s"
    translation_page_duration_ms: str = "{M}m {S}s"
    translation_page_duration_s: str = "{S}s"
    translation_page_token_detail: str = "Output: {OUTPUT} · Input: {INPUT}"
    translation_page_thread_title: str = "Thread Health"
    translation_page_thread_unit: str = "Active"
    translation_page_thread_detail: str = "Running {RUNNING}/{MAX} · Failed retries {FAILED}"
    translation_page_feed_title: str = "Recent Translation Stream"
    translation_page_feed_mode: str = "Live status"
    translation_page_feed_empty: str = "Waiting for translation stream data"
    translation_page_footer_backup: str = "Automatic snapshot backup enabled"
    proofreading_page_header_description: str = "Review, correct, and confirm results in the bilingual table"
    project_page_header_description: str = "Bind a Ren'Py project and configure translation input and output folders"
    app_settings_page_header_description: str = "Manage language, updates, sound, and application display options"
    basic_settings_page_header_description: str = "Adjust concurrency, timeout, and retry thresholds for translation tasks"
    expert_settings_page_header_description: str = "Control prompts, asset analysis, and result checking behavior"
    custom_prompt_page_header_description: str = "Configure translation prompt modes, styles, and preview content"
    app_basic_settings_page: str = "Basic Settings"
    app_expert_settings_page: str = "Expert Settings"
    app_glossary_page: str = "Glossary"
    app_text_preserve_page: str = "Text Preserve"
    app_text_replacement_page: str = "Text Replacement"
    app_pre_translation_replacement_page: str = "Pre-Translation"
    app_post_translation_replacement_page: str = "Post-Translation"
    app_custom_prompt_navigation_item: str = "Translation Prompts"
    app_custom_prompt_zh_page: str = "Chinese Prompts"
    app_custom_prompt_en_page: str = "English Prompts"
    app_laboratory_page: str = "Laboratory"
    app_treasure_chest_page: str = "Treasure Chest"

    # 路径
    path_bilingual: str = "bilingual"
    path_glossary_export: str = "export_glossary"
    path_text_preserve_export: str = "export_text_preserve"
    path_pre_translation_replacement_export: str = "export_pre_translation_replacement"
    path_post_translation_replacement_export: str = "export_post_translation_replacement"
    path_result_check_kana: str = "result_check_residual_kana.json"
    path_result_check_hangeul: str = "result_check_residual_hangeul.json"
    path_result_check_text_preserve: str = "result_check_text_preserve.json"
    path_result_check_similarity: str = "result_check_high_similarity.json"
    path_result_check_glossary: str = "result_check_incorrect_glossary.json"
    path_result_check_mixed_translation: str = "result_check_mixed_translation.json"
    path_result_check_untranslated: str = "result_check_untranslated_entries.json"
    path_result_check_retry_count_threshold: str = "result_check_retry_count_reach_threshold.json"
    path_result_batch_correction: str = "batch_correction.xlsx"
    path_result_name_field_extraction: str = "name_field_extraction.xlsx"

    # 日志
    log_proxy: str = "Network proxy enabled …"
    log_expert_mode: str = "Expert Mode Enabled …"
    log_api_test_fail: str = "API test failed … "
    log_task_fail: str = "Translation task failed …"
    log_read_file_fail: str = "File reading failed …"
    log_write_file_fail: str = "File writing failed …"
    log_read_cache_file_fail: str = "Failed to read cached data from file …"
    log_write_cache_file_fail: str = "Failed to write cached data to file …"
    log_no_cache_data: str = "No cache data found. Run a translation first …"
    log_crash: str = "A critical error has occurred, program will now exit. Error detail has been saved to the log file …"
    cli_verify_folder: str = "parameter error: invalid path …"
    cli_verify_language: str = "parameter error: invalid language …"
    translator_max_round: str = "Max rounds"
    translator_current_round: str = "Current round"
    translator_api_url: str = "API URL"
    translator_name: str = "API Name"
    translator_model: str = "Model Name"
    translator_writing: str = "Writing translation data, please wait …"
    translator_done: str = "All texts are translated, translation task finished …"
    translator_fail: str = "Maximum translation rounds reached, some texts are still untranslated. Please check the translation results …"
    translator_stop: str = "Translation task stopped …"
    translator_write: str = "Translation result saved to {PATH} directory …"
    translator_task_generation_log: str = "Task generation completed, {COUNT} tasks generated in total …"
    translator_rule_filter_log: str = "Rule filtering completed, {COUNT} entries that do not require translation were filtered in total …"
    translator_language_filter_log: str = "Language filtering completed, {COUNT} entries not containing the target language were filtered in total …"
    translator_mtool_optimizer_pre_log: str = "MToolOptimizer pre-processing completed, {COUNT} entries containing duplicate clauses were filtered in total …"
    translator_mtool_optimizer_post_log: str = "MToolOptimizer post-processing completed …"
    translator_task_response_think: str = "Model thinking:\n"
    translator_task_response_result: str = "Model response:\n"
    translator_response_check_fail: str = "Translated text failed check, will automatically retry in the next round of translation"
    translator_response_check_fail_all: str = "All translated text failed check, will automatically retry in the next round of translation"
    translator_response_check_fail_part: str = "Partial translated text failed check, will automatically retry in the next round of translation"
    translator_response_check_fail_line_stats: str = "failed lines {FAILED}/{TOTAL}"
    translator_single_line_mode_summary: str = "Single-line mode: requested {REQUESTED} lines, plain-text fallback {FALLBACK} lines, failed {FAILED} lines, parse failures {MISMATCH} lines"
    translator_task_success: str = "Task time {TIME} seconds, {LINES} lines of text, input tokens {PT}, output tokens {CT}"
    translator_too_many_task: str = "Too many real-time tasks. Details hidden for performance …"
    translator_no_items: str = "No translatable data was found. Please check that the input file and project settings are correct …"
    translator_running: str = "Task is running, please try again later …"
    file_checker_kana: str = "Kana residue check complete, no issues found …"
    file_checker_kana_full: str = "Kana residue check complete, {COUNT} issues found, {PERCENT}%, results written to [green]{TARGET}[/] …"
    file_checker_hangeul: str = "Hangeul residue check complete, no issues found …"
    file_checker_hangeul_full: str = "Hangeul residue check complete, {COUNT} issues found, {PERCENT}%, results written to [green]{TARGET}[/] …"
    file_checker_text_preserve: str = "Text preservation check completed, no issues found …."
    file_checker_text_preserve_full: str = "Text preservation check completed, found {COUNT} potential issues ({PERCENT}%), results written to [green]{TARGET}[/] …."
    file_checker_text_preserve_alert_key: str = "____ALERT____"
    file_checker_text_preserve_alert_value: str = "This file lists entries where text preservation **might** not have worked correctly. Please verify in context!!"
    file_checker_similarity: str = "Similarity check complete, no issues found …"
    file_checker_similarity_full: str = "Similarity check complete, {COUNT} potential issues found, {PERCENT}%, results written to [green]{TARGET}[/] …"
    file_checker_similarity_alert_key: str = "____ALERT____"
    file_checker_similarity_alert_value: str = "This file lists entries with *potentially* high similarity. Please verify in context!"
    file_checker_glossary: str = "Glossary check complete, no issues found …"
    file_checker_glossary_full: str = "Glossary check complete, {COUNT} issues found, {PERCENT}%, results written to [green]{TARGET}[/] …"
    file_checker_mixed_translation: str = "Mixed-language check complete, no issues found …"
    file_checker_mixed_translation_full: str = "Mixed-language check complete, {COUNT} issues found, {PERCENT}%, results written to [green]{TARGET}[/] …"
    platofrm_tester_key: str = "Testing API Key"
    platofrm_tester_messages: str = "Task prompts:"
    platofrm_tester_response_think: str = "Model thinking:"
    platofrm_tester_response_result: str = "Model response:"
    platofrm_tester_result: str = "Tested {COUNT} APIs in total, {SUCCESS} successful, {FAILURE} failed …"
    platofrm_tester_result_failure: str = "Failed Keys:"
    platofrm_tester_running: str = "Task is running, please try again later …"
    response_checker_unknown: str = "Unknown"
    response_checker_fail_data: str = "Data Structure Error"
    response_checker_fail_line_count: str = "Line Count Mismatch"
    response_checker_line_error_kana: str = "Kana Residue"
    response_checker_line_error_hangeul: str = "Hangeul Residue"
    response_checker_line_error_fake_reply: str = "Fake-Reply Residue"
    response_checker_line_error_empty_line: str = "Empty Line"
    response_checker_line_error_mixed_language: str = "Mixed-Language Leakage"
    response_checker_line_error_similarity: str = "High Similarity"
    response_checker_line_error_degradation: str = "Degradation Occurred"
    response_decoder_glossary_by_json: str = "Glossary data -> deserialization, total {COUNT} entries"
    response_decoder_glossary_by_rule: str = "Glossary data -> rule parsing after split, total {COUNT} entries"
    response_decoder_translation_by_json: str = "Translation data -> deserialization, total {COUNT} entries"
    response_decoder_translation_by_rule: str = "Translation data -> rule parsing after split, total {COUNT} entries"

    # 应用设置
    app_update_group_title: str = "About and Updates"
    app_update_group_description: str = "View the current version and check for updates"
    app_update_current_version: str = "Current Version"
    app_update_check: str = "Check for Updates"
    app_update_checking: str = "Checking…"
    app_update_status_not_checked: str = "Updates have not been checked"
    app_update_status_check_failed: str = "Update check failed. Try again"
    app_update_status_latest: str = "You're up to date"
    app_update_status_new: str = "New version available: {VERSION}"
    app_update_status_downloading: str = "Downloading {DOWNLOADED} / {TOTAL}"
    app_update_status_downloaded: str = "Download complete, restart to apply"
    app_update_view_details: str = "View Details"
    app_update_cancel: str = "Cancel"
    app_update_cancelling: str = "Cancelling…"
    app_update_install: str = "Restart and Install"
    app_update_install_busy: str = "A task is running. Installing the update will interrupt it and restart the app. Continue?"
    app_update_changelog_title: str = "Changelog"
    app_update_changelog_description: str = "Review changes and fixes by version"
    app_update_changelog_action: str = "View Changelog"
    app_update_details_title: str = "New Version {VERSION}"
    app_update_notes_empty: str = "No release notes are available for this version"
    app_update_release_metadata: str = "Package {SIZE} · Published {DATE}"
    app_update_size_unknown: str = "Size unknown"
    app_update_date_unknown: str = "Date unknown"
    app_update_download: str = "Download Update"
    app_update_check_latest_toast: str = "You're using the latest version"
    app_update_check_failure: str = "Update check failed: "
    app_update_cancelled: str = "Download cancelled"
    toast_merged_count: str = " (x{})"
    app_changelog_title: str = "Changelog"
    app_changelog_empty: str = "No changelog is available"
    app_changelog_available: str = "Update available: {VERSION}"
    app_changelog_open_browser: str = "Open Full History in Browser"
    app_settings_page_startup_sound_title: str = "Startup Sound"
    app_settings_page_startup_sound_content: str = "Play a sound when the app starts (default: off)"
    app_settings_page_language_title: str = "Application Language"
    app_settings_page_language_content: str = "Choose the interface language; changes take effect after restart"
    app_settings_page_language_zh: str = "简体中文"
    app_settings_page_language_en: str = "English"
    app_settings_page_expert_title: str = "Expert Mode"
    app_settings_page_expert_content: str = "Enabling this feature will display more log information and provide more advanced setting options (takes effect after app restart)"
    app_settings_page_font_hinting_title: str = "Font Hinting"
    app_settings_page_font_hinting_content: str = "Enabling this feature will render the edges of UI fonts more smoothly (takes effect after app restart)"
    app_settings_page_scale_factor_title: str = "Global Scale Factor"
    app_settings_page_scale_factor_content: str = "Enabling this feature will scale the app interface according to the selected ratio (takes effect after app restart)"
    app_settings_page_proxy_url: str = "Example - http://127.0.0.1:7890"
    app_settings_page_proxy_url_title: str = "Network Proxy"
    app_settings_page_proxy_url_content: str = "Enabling this feature will use the set proxy address to send network requests  (takes effect after app restart)"
    app_settings_page_close: str = "The application will close, please confirm …"

    # 接口管理
    platform_page_api_test_result: str = "API test result: {SUCCESS} successful, {FAILURE} failed …"
    platform_page_api_activate: str = "Activate API"
    platform_page_api_edit: str = "Edit API"
    platform_page_api_args: str = "Edit Arguments"
    platform_page_api_test: str = "Test API"
    platform_page_api_delete: str = "Delete API"
    platform_page_widget_add_title: str = "API List"
    platform_page_widget_add_content: str = "Add and manage translation APIs compatible with Google, OpenAI, Anthropic, DeepL and DeepLX here"
    platform_page_header_description: str = "Manage translation APIs, model parameters, and the active channel"
    platform_page_active_hint: str = "Active API: {NAME}"
    platform_page_active_none: str = "No active API selected"
    platform_page_empty_title: str = "No APIs yet"
    platform_page_empty_content: str = 'Click "Add" in the top-right corner to create your first API'
    platform_page_group_local_title: str = "Local Models"
    platform_page_group_local_content: str = "Model APIs deployed locally or on the local network"
    platform_page_group_machine_title: str = "Machine Translation"
    platform_page_group_machine_content: str = "Non-LLM translation APIs such as DeepL and DeepLX"
    platform_page_group_online_title: str = "Online LLMs"
    platform_page_group_online_content: str = "Online large language model APIs provided by various platforms"
    platform_page_group_custom_title: str = "Custom APIs"
    platform_page_group_custom_content: str = "Third-party or self-configured APIs"

    # 接口编辑
    platform_edit_page_name: str = "Please enter API name …"
    platform_edit_page_name_title: str = "API Name"
    platform_edit_page_name_content: str = "Please enter API name, only for display within the app, no practical effect"
    platform_edit_page_api_url: str = "Please enter API URL …"
    platform_edit_page_api_url_title: str = "API URL"
    platform_edit_page_api_url_content: str = "Please enter API URL, pay attention to whether /v1 needs to be added at the end"
    platform_edit_page_api_key: str = "Please enter API Key …"
    platform_edit_page_api_key_title: str = "API Key"
    platform_edit_page_api_key_content: str = "Please enter API Key, e.g., sk-d0daba12345678fd8eb7b8d31c123456. Multiple keys can be entered for polling, one key per line"
    platform_edit_page_api_key_clear_failed: str = "Credential cleanup failed; the existing key was kept"
    platform_edit_page_api_key_save_failed: str = "Failed to save the API key; please try again"
    platform_edit_page_thinking_title: str = "Thinking Level"
    platform_edit_page_thinking_content: str = "Set model thinking level (OFF/LOW/MEDIUM/HIGH/MAX), only works for models that support thinking mode"
    platform_edit_page_thinking_off: str = "Off"
    platform_edit_page_thinking_low: str = "Low"
    platform_edit_page_thinking_medium: str = "Medium"
    platform_edit_page_thinking_high: str = "High"
    platform_edit_page_thinking_max: str = "Max"
    platform_edit_page_model: str = "Please enter Model Name …"
    platform_edit_page_model_title: str = "Model Name"
    platform_edit_page_model_content: str = "Current model in use: {MODEL}"
    platform_edit_page_model_edit: str = "Manual Input"
    platform_edit_page_model_sync: str = "Fetch Online"

    # 参数编辑
    args_edit_page_top_p_title: str = "top_p"
    args_edit_page_top_p_content: str = "Please set with caution, incorrect values may cause abnormal results or request errors"
    args_edit_page_temperature_title: str = "temperature"
    args_edit_page_temperature_content: str = "Please set with caution, incorrect values may cause abnormal results or request errors"
    args_edit_page_presence_penalty_title: str = "presence_penalty"
    args_edit_page_presence_penalty_content: str = "Please set with caution, incorrect values may cause abnormal results or request errors"
    args_edit_page_frequency_penalty_title: str = "frequency_penalty"
    args_edit_page_frequency_penalty_content: str = "Please set with caution, incorrect values may cause abnormal results or request errors"
    args_edit_page_document_link: str = "Click to view documentation"

    # 模型列表
    model_list_page_title: str = "Available Model List"
    model_list_page_content: str = "Click to select the model to use"
    model_list_page_fail: str = "Failed to get model list, please check API configuration …"

    # 项目设置
    project_page_source_language_title: str = "Source Language"
    project_page_source_language_content: str = "Set the language of the input text in the current project"
    project_page_target_language_title: str = "Target Language"
    project_page_target_language_content: str = "Set the language of the output text in the current project"
    project_page_input_folder_title: str = "Input Folder"
    project_page_input_folder_content: str = "The current input folder is"
    project_page_output_folder_title: str = "Output Folder (Can not be same as input folder)"
    project_page_output_folder_content: str = "The current output folder is"
    project_page_output_folder_open_on_finish_title: str = "Open Output Folder on Task Completion"
    project_page_output_folder_open_on_finish_content: str = "When enabled, the output folder will be automatically opened upon task completion"
    project_page_traditional_chinese_title: str = "Output Chinese in Traditional Characters"
    project_page_traditional_chinese_content: str = "When enabled, Chinese text will be output in Traditional characters if the target language is set to Chinese"

    # 开始翻译
    translation_page_status_idle: str = "Idle"
    translation_page_status_testing: str = "Testing"
    translation_page_status_translating: str = "Translating"
    translation_page_status_stopping: str = "Stopping"
    translation_page_status_polishing: str = "AI Polishing"
    translation_page_status_proofreading: str = "AI Proofreading"
    translation_page_status_stopping_polishing: str = "Stopping AI Polish"
    translation_page_status_stopping_proofreading: str = "Stopping AI Proofread"
    translation_page_indeterminate_saving: str = "Saving cache file …"
    translation_page_indeterminate_stoping: str = "Stopping translation task …"
    translation_page_card_time: str = "Elapsed Time"
    translation_page_card_remaining_time: str = "Remaining Time"
    translation_page_card_line: str = "Translated Lines"
    translation_page_card_remaining_line: str = "Remaining Lines"
    translation_page_card_speed: str = "Average Speed"
    translation_page_card_token: str = "Total Tokens"
    translation_page_card_token_input: str = "Input Tokens"
    translation_page_card_token_output: str = "Output Tokens"
    translation_page_card_token_tooltip: str = "Click to toggle Input/Output"
    translation_page_card_task: str = "Real Time Tasks"
    translation_page_alert_pause: str = "Stopped translation tasks can be resumed at any time. Confirm to stop the task … ?"
    translation_page_continue: str = "Continue Task"
    translation_page_export: str = "Export Task Data"
    translation_page_export_tooltip: str = "Export translation file"
    translation_page_reinject_cache: str = "Reinject from Cache"
    translation_page_reinject_cache_tooltip: str = "Rewrite translations from cache to the output folder"
    translation_page_reinject_cache_confirm: str = "This will rewrite translation files from cache. Continue?"
    translation_page_reinject_cache_success: str = "Cache reinjection completed"
    translation_page_reinject_cache_no_cache: str = "No cache data found, please translate first"
    translation_page_timer: str = "Waiting time before delayed startup"
    translation_page_preflight_missing_assets_title: str = "No usable project assets"
    translation_page_preflight_missing_assets_content: str = "No enabled and valid worldbook, character card, glossary, or do-not-translate entry was found. Open the workbench to prepare project assets, or continue this translation anyway."
    translation_page_preflight_open_workbench: str = "Open Workbench"
    translation_page_preflight_continue: str = "Continue Anyway"
    translation_page_preflight_load_error: str = "Could not load project assets, so translation was not started: {ERROR}"
    translation_page_preflight_workbench_unavailable: str = "The workbench could not be opened. Use the Character / Worldbook Workbench in the sidebar."

    # Proofreading
    proofreading_page_load: str = "Load"
    proofreading_page_save: str = "Save"
    proofreading_page_save_tooltip: str = "Shortcut Ctrl + S"
    proofreading_page_export: str = "Export"
    proofreading_page_search: str = "Search"
    proofreading_page_filter: str = "Filter"
    proofreading_page_current_view: str = "Current view"
    proofreading_page_retranslate: str = "Retranslate"
    proofreading_page_confirm_translation: str = "Mark Translation as Correct"
    proofreading_page_confirm_selected_translations: str = "Mark Selected Translations as Correct"
    proofreading_page_confirm_translation_done: str = "Marked {COUNT} translations as correct; click Save to persist"
    proofreading_page_copy_src: str = "Copy Source"
    proofreading_page_copy_src_done: str = "Source copied to clipboard"
    proofreading_page_copy_dst: str = "Copy Translation"
    proofreading_page_copy_dst_done: str = "Translation copied to clipboard"
    proofreading_page_save_success: str = "Data saved"
    proofreading_page_export_success: str = "Export completed"
    proofreading_page_export_failed: str = "Export failed"
    proofreading_page_export_confirm: str = "Confirm to export the translation file?"
    proofreading_page_export_tooltip: str = "Export translation file\nSave the data first, then generate the translation file"
    proofreading_page_col_src: str = "Source"
    proofreading_page_col_dst: str = "Translation"
    proofreading_page_col_status: str = "Status"
    proofreading_page_no_cache: str = "No cache file found, please run translation task first"
    proofreading_page_load_failed: str = "Failed to read cache file"
    proofreading_page_save_failed: str = "Save failed"
    proofreading_page_retranslate_confirm: str = "Confirm to retranslate this entry?"
    proofreading_page_retranslate_failed: str = "Translation failed, please retry"
    proofreading_page_retranslate_success: str = "Translation completed"
    proofreading_page_batch_replace: str = "Batch Replace"
    proofreading_page_batch_retranslate: str = "Batch Retranslate"
    proofreading_page_batch_reset_translation: str = "Batch Reset"
    proofreading_page_batch_no_selection: str = "Please select entries first"
    proofreading_page_batch_replace_action: str = "Batch Replace"
    proofreading_page_batch_replace_find: str = "Find"
    proofreading_page_batch_replace_with: str = "Replace With"
    proofreading_page_batch_replace_options: str = "Replace Options"
    proofreading_page_batch_replace_regex: str = "Use Regex"
    proofreading_page_batch_replace_case_sensitive: str = "Case Sensitive"
    proofreading_page_batch_replace_scope: str = "Replace Scope"
    proofreading_page_batch_replace_scope_selected: str = "Selected entries ({COUNT})"
    proofreading_page_batch_replace_scope_filtered: str = "Current filtered entries ({COUNT})"
    proofreading_page_batch_replace_empty_keyword: str = "Please enter find text first"
    proofreading_page_batch_replace_invalid_regex: str = "Invalid regular expression"
    proofreading_page_batch_replace_done: str = "Batch replace done: {N} entries changed"
    proofreading_page_batch_replace_no_change: str = "No content needs replacement"
    proofreading_page_batch_retranslate_confirm: str = "Confirm to batch retranslate {COUNT} selected entries?"
    proofreading_page_batch_retranslate_done: str = "Batch retranslate done: {SUCCESS} success, {FAILURE} failed"
    proofreading_page_batch_reset_translation_confirm: str = "Confirm to batch reset {COUNT} selected entries?"
    proofreading_page_batch_reset_translation_done: str = "Batch reset done: {N} entries changed"
    proofreading_page_warning_tooltip_title: str = "Result Check"
    proofreading_page_filter_warning_type: str = "Result Check"
    proofreading_page_filter_status: str = "Translation Status"
    proofreading_page_filter_file: str = "File"
    proofreading_page_filter_glossary_terms: str = "Glossary Details"
    proofreading_page_status_none: str = "Untranslated"
    proofreading_page_status_processed: str = "Completed"
    proofreading_page_status_polished: str = "Polished"
    proofreading_page_status_processed_in_past: str = "Previously Completed"
    proofreading_page_page_info: str = "Page {CURRENT} / {TOTAL}"
    proofreading_page_warning_kana: str = "Kana Residue"
    proofreading_page_warning_hangeul: str = "Hangeul Residue"
    proofreading_page_warning_text_preserve: str = "Text Preserve Failed"
    proofreading_page_warning_similarity: str = "High Similarity"
    proofreading_page_warning_glossary: str = "Glossary Not Applied"
    proofreading_page_warning_retry: str = "Retry Threshold Reached"
    proofreading_page_filter_select_all: str = "Select All"
    proofreading_page_filter_no_warning: str = "No Warning"
    proofreading_page_filter_clear: str = "Clear"
    proofreading_page_filter_no_glossary_error: str = "No glossary warnings"
    proofreading_page_filter_export: str = "Export Report"
    proofreading_page_filter_export_tooltip: str = "Export filtered items to file"
    proofreading_page_filter_export_success: str = "Filtered report exported"
    proofreading_page_filter_export_failed: str = "Failed to export filtered report"
    proofreading_page_indeterminate_loading: str = "Loading data …"
    proofreading_page_indeterminate_saving: str = "Saving data …"
    proofreading_page_indeterminate_exporting: str = "Exporting data …"
    proofreading_page_ai_polish: str = "Polish Selected Translations"
    proofreading_page_ai_polish_tooltip: str = "Improve the expression, style, and character voice of selected translations"
    proofreading_page_ai_proofread: str = "Proofread Selected Translations"
    proofreading_page_ai_proofread_tooltip: str = "Check selected translations against glossary, placeholders, and quality warnings"
    proofreading_page_quality_report: str = "Quality Check Report"
    proofreading_page_quality_report_tooltip: str = "Review detected issues, select entries, and start AI proofreading"
    proofreading_page_quality_cancel: str = "Stop AI Task"
    proofreading_page_quality_cancel_tooltip: str = "Cancel the current AI request immediately; completed batches are kept"
    proofreading_page_quality_no_polishable: str = "The selected entries contain no translated text that can be polished"
    proofreading_page_quality_no_proofreadable: str = "The selected entries contain no translation that can be proofread"
    proofreading_page_quality_confirm_polish: str = "Polish the selected {COUNT} translations?"
    proofreading_page_quality_confirm_proofread: str = "Proofread the selected {COUNT} translations?"
    proofreading_page_quality_start_failed: str = "Unable to start the quality task; check the translation snapshot and provider configuration"
    proofreading_page_quality_progress: str = "{TASK}: processed {PROCESSED}/{TOTAL}, updated {UPDATED}, failed {FAILED}"
    proofreading_page_quality_done: str = "{TASK} completed: updated {UPDATED}, failed {FAILED}, skipped {SKIPPED}"
    proofreading_page_quality_cancelled: str = "The quality task stopped; completed batches were saved"
    proofreading_page_quality_cancelling: str = "Stopping quality task …"
    proofreading_page_quality_report_title: str = "Translation Quality Check Report"
    proofreading_page_quality_report_failed: str = "Failed Entries"
    proofreading_page_quality_report_fallback: str = "Fallback Entries"
    proofreading_page_quality_report_alignment: str = "Index/Line Mismatches"
    proofreading_page_quality_report_error_types: str = "Error types: {ERRORS}"
    proofreading_page_quality_report_items: str = "Select entries to proofread"
    proofreading_page_quality_report_empty: str = "The cache has no locatable quality-failure entries"
    proofreading_page_quality_report_proofread: str = "Proofread Selected Entries"
    translation_page_status_quality: str = "Quality Processing"
    translation_page_status_agent: str = "Agent operation"

    # Agent page
    agent_page_title: str = "Agent Assistant"
    agent_page_description: str = "Current project"
    agent_page_project_unset: str = "Project not set"
    agent_page_project_context: str = "{name} · {language}"
    agent_page_platform: str = "Agent API"
    agent_page_platform_unset: str = "Agent API not set"
    agent_page_platform_saved: str = "Agent API saved"
    agent_page_refresh: str = "Refresh"
    agent_page_input_placeholder: str = "Describe the project task …"
    agent_page_send: str = "Send"
    agent_page_stop: str = "Stop"
    agent_page_running: str = "Working …"
    agent_page_cancelled: str = "Stop requested"
    agent_page_done: str = "Done"
    agent_page_failed: str = "Failed"
    agent_page_assistant_label: str = "Agent"
    agent_page_thinking_process: str = "Thinking"
    agent_page_user_label: str = "You"
    agent_page_error_label: str = "Error"
    agent_page_empty_title: str = "New task"
    agent_page_empty_description: str = "This conversation is empty"
    agent_page_suggestion_project: str = "Inspect the project and suggest the next step"
    agent_page_suggestion_rpa: str = "List RPA files in the project"
    agent_page_suggestion_errors: str = "Scan project script errors"
    agent_page_suggestion_old_new: str = "Fix old/new translations not taking effect"
    agent_page_suggestion_project_desc: str = "Summarize unpacking, translation, assets, and quality"
    agent_page_suggestion_rpa_desc: str = "List RPA archives in the game folder"
    agent_page_suggestion_errors_desc: str = "Scan for common script errors without modifying files"
    agent_page_suggestion_old_new_desc: str = "Generate a runtime replacement patch after translation"
    agent_page_tool_expand: str = "Show details"
    agent_page_tool_running: str = "Running"
    agent_page_tool_done: str = "Done"
    agent_page_tool_failed: str = "Failed"
    agent_page_tool_calling: str = "Calling tool"
    agent_page_tool_prefix: str = "Tool"
    agent_page_tool_set_project: str = "Set project"
    agent_page_tool_get_project_info: str = "Read project details"
    agent_page_tool_inspect_translation_project: str = "Inspect translation status"
    agent_page_tool_list_rpa_files: str = "Find RPA files"
    agent_page_tool_scan_script_errors: str = "Scan script errors"
    agent_page_tool_unpack_rpa_files: str = "Unpack RPA files"
    agent_page_tool_optimize_old_new_translations: str = "Build supplement fallback"
    agent_page_action_open_translation: str = "Open Translation"
    agent_page_action_one_key_translate: str = "Start One-click Translation"
    agent_page_action_continue_translation: str = "Continue Translation"
    agent_page_action_open_workbench: str = "Open Character / Worldbook Workbench"
    agent_page_action_open_toolbox: str = "Open Ren'Py Toolbox"
    agent_page_action_unpack_rpa_prompt: str = "Unpack the RPA files in the current project"
    agent_page_one_key_unavailable: str = "One-click translation cannot start right now. Check the project and try again."
    agent_page_confirmation_title: str = "Confirm RPA Unpacking"
    agent_page_confirmation_generic: str = "The Agent is about to run {tool}. Continue?"
    agent_page_waiting_confirmation: str = "Waiting for confirmation"
    agent_page_unpack_confirmation: str = (
        "The Agent is about to unpack {count} RPA file(s) in the current project:\n{game_dir}\n\n"
        "Files will be written directly into the game folder and may overwrite files with the same name. "
        "The original RPA files will be kept. Continue?"
    )
    agent_page_old_new_confirmation_title: str = "Confirm supplement fallback"
    agent_page_old_new_confirmation: str = (
        "Current language folder:\n{tl_dir}\n\n"
        "Supplemental extraction entries: {old_new_count}\n"
        "Independent supplement entries: {supplement_count}\n"
        "Final replacements: {total_count}\n"
        "Conflicting sources skipped: {conflict_count}\n\n"
        "A runtime replacement script will be generated from longest source text to shortest:\n"
        "{output_path}\n\n"
        "If an automatic supplement hook already exists, it will be backed up before replacement. Continue?"
    )
    agent_page_new_task: str = "New task"
    agent_page_round: str = "Round {round}"
    agent_page_topbar_api: str = "API"
    agent_page_settings_title: str = "Agent Settings"
    agent_page_settings_refresh: str = "Refresh API list"
    agent_page_settings_unpack_confirm: str = "Confirm before unpacking RPA"
    agent_page_unpack_dont_ask: str = "Always unpack automatically without asking"
    agent_page_retry: str = "Retry"
    agent_page_user_avatar: str = "You"
    agent_page_send_hint: str = "Ctrl + Enter to send"
    agent_page_copy: str = "Copy"
    agent_page_copied: str = "Copied to clipboard"
    agent_page_stopped_hint: str = "Generation stopped"
    agent_page_scroll_latest: str = "Back to latest message"
    agent_page_platform_changed_hint: str = (
        "Agent API switched. This conversation still uses the previous API context; "
        "click \"New task\" for a fresh context."
    )
    agent_page_tool_detail_truncated: str = (
        "Detail truncated: showing first {shown} of {total} characters. Hover for the full text."
    )

    # Agent tools
    agent_tool_set_project_description: str = (
        "Set the Ren'Py project path explicitly provided by the user and return "
        "the normalized root, game folder, and language."
    )
    agent_tool_project_path_description: str = (
        "A project path explicitly provided by the user in the conversation."
    )
    agent_tool_get_project_info_description: str = (
        "Read the current project paths and language; return PROJECT_NOT_SET "
        "when no project is configured."
    )
    agent_tool_inspect_translation_project_description: str = (
        "Read-only inspection of scripts, RPA files, translation cache, workbench assets, "
        "quality issues, and old/new status. Return a stable next-step recommendation "
        "without starting translation or modifying files."
    )
    agent_tool_list_rpa_files_description: str = (
        "List RPA files in the current project game folder. The server injects the path."
    )
    agent_tool_scan_script_errors_description: str = (
        "Scan Ren'Py script errors in the current project game folder without modifying files."
    )
    agent_tool_unpack_rpa_files_description: str = (
        "Unpack all RPA files in the current project game folder. The server injects the path, "
        "the user must confirm overwrite risk, and original archives are kept."
    )
    agent_tool_optimize_old_new_translations_description: str = (
        "After translation, read entries marked as supplemental extraction results from the current "
        "language folder and generate a longest-first replace_text runtime fallback. Officially "
        "extracted old/new entries are excluded."
    )
    agent_project_inspection_complete: str = (
        "Project inspection complete: {rpy_count} RPY, {rpyc_count} RPYC, {rpa_count} RPA; "
        "{item_count} cached entries with {untranslated_count} untranslated. "
        "Recommended next step: {next_action}."
    )
    agent_inspection_action_unpack_rpa: str = "unpack the RPA files first"
    agent_inspection_action_decompile_scripts: str = "decompile the RPYC scripts first"
    agent_inspection_action_repair_cache: str = "inspect or repair the translation cache first"
    agent_inspection_action_review_workbench: str = "review and apply the workbench drafts first"
    agent_inspection_action_start_translation: str = "start translation on the translation page"
    agent_inspection_action_continue_translation: str = "continue the unfinished translation"
    agent_inspection_action_review_quality: str = "resolve the translation quality issues first"
    agent_inspection_action_refresh_replace_fallback: str = "regenerate the replace_text fallback"
    agent_inspection_action_review_translation: str = "review and apply the translation results"
    agent_inspection_action_check_project_files: str = "check the project for processable scripts"
    agent_system_prompt: str = (
        "You are the RenpyBox project assistant. Use only the tools currently provided.\n"
        "Only call set_project(path) when the user explicitly provides a path. Other tools have no path "
        "arguments and must use the current project injected by the server. Never guess or construct paths.\n"
        "When a tool returns PROJECT_NOT_SET, explain that no project is set and ask for the game path. "
        "After the user provides it, call set_project and continue the original task.\n"
        "When the user asks about project state, translation progress, or what to do next, call "
        "inspect_translation_project first. It is read-only; explain its next_action_code without "
        "claiming that the recommended action has already run.\n"
        "unpack_rpa_files writes into the current game folder and may run only after the user confirms the "
        "overwrite risk in the UI. Do not claim that you can delete RPA files, choose an output path, or stop "
        "an external unpack process after it starts. A clear request sent by a UI action button should call the "
        "corresponding tool directly; confirmation is handled by the UI Confirm and Cancel buttons, so do not "
        "ask for it again in text. Do not use Emoji or colored Unicode status icons in replies; the UI renders "
        "status and action icons. Translation itself belongs to the translation page; do not "
        "retranslate through the Agent. Only call optimize_old_new_translations after translations are applied "
        "and the user asks to fix supplemental extraction text, or when inspection "
        "returns REFRESH_REPLACE_FALLBACK and the user asks to apply that recommendation. Require confirmation. "
        "Summarize key results; full details are shown in the UI."
    )

    # Agent runtime
    agent_request_schema_only: str = "Schema only."
    agent_request_unsupported_platform: str = "This API does not support Agent tools. Select an OpenAI, Anthropic, or Google API."
    agent_request_unsupported_format: str = "This API format does not support Agent tools."
    agent_request_no_tools: str = "No Agent tools are available."
    agent_request_cancelled: str = "The Agent request was cancelled."
    agent_request_bad_request: str = "The model rejected the Agent request parameters."
    agent_request_failed: str = "The Agent request failed. Check the API settings or network connection."
    agent_tool_arguments_must_be_object: str = "Tool arguments must be a JSON object."
    agent_tool_undeclared_arguments: str = "Undeclared arguments: {names}."
    agent_tool_missing_arguments: str = "Missing required arguments: {names}."
    agent_tool_argument_must_be_string: str = "Argument {name} must be a string."
    agent_tool_argument_must_be_object: str = "Argument {name} must be an object."
    agent_tool_unknown: str = "Unknown tool: {name}"
    agent_tool_confirmation_required: str = "This operation requires user confirmation."
    agent_tool_confirmation_stale: str = "The confirmation context expired. Review the operation and confirm it again."
    agent_tool_engine_busy: str = "The engine is busy, so this operation cannot run now."
    agent_tool_invalid_result: str = "The tool returned an invalid result."
    agent_tool_failed_logged: str = "The tool failed. Details were written to the log."
    agent_tool_cancelled: str = "Cancelled. The tool was not run."
    agent_api_unset: str = "No Agent API is selected. Choose an OpenAI, Anthropic, or Google API on the Agent page."
    agent_api_missing: str = "The selected Agent API no longer exists. Select it again."
    agent_task_empty: str = "Enter a task to run."
    agent_api_not_set: str = "The Agent API is not set."
    agent_reply_empty: str = "The Agent did not return any displayable content."
    agent_confirmation_timeout: str = "Confirmation timed out. The tool was not run."
    agent_project_changed: str = "The project changed. Review the operation and confirm it again."
    agent_max_iterations: str = "The Agent reached the maximum number of tool rounds and stopped."
    agent_project_not_set_ask: str = "No project is set. Ask the user for the game folder, then call set_project."
    agent_project_not_set: str = "No project is set. Set a project first."
    agent_project_path_empty: str = "The project path cannot be empty."
    agent_project_path_invalid: str = "The path does not look like a valid Ren'Py project (a game or tl folder is required)."
    agent_project_game_not_found: str = "An existing game folder could not be found. The project setting was not changed."
    agent_project_set: str = "Project set: {project_root} (language: {language})"
    agent_project_current: str = "Current project: {project_root} (language: {language})"
    agent_rpa_not_found: str = "No RPA files were found in the current project."
    agent_rpa_found: str = "Found {count} RPA file(s) in the current project: {files}"
    agent_scan_no_errors: str = "Script scan completed with no errors found."
    agent_scan_errors: str = "Script scan completed with {total} issue(s); the first {returned} are included."
    agent_unpack_project_changed: str = "The project folder changed. Review the operation and confirm it again."
    agent_unpack_complete: str = "RPA unpacking completed for {count} archive(s). The original RPA files were kept."
    agent_unpack_failed: str = "RPA unpacking failed. Check the log for details."
    agent_old_new_translation_not_found: str = "No translated supplemental extraction entries were found in the current language folder."
    agent_old_new_optimization_complete: str = "Generated the supplemental runtime fallback with {count} entries: {output_path}"
    agent_old_new_stale_hook_removed: str = "Removed the stale replace_text patch because no supplemental translations remain: {output_path}"

    # 基础设置
    basic_settings_page_max_workers_title: str = "Concurrent Task Threshold"
    basic_settings_page_max_workers_content: str = (
        "Maximum number of tasks executing simultaneously"
        "<br>"
        "The default is 16; proper configuration can significantly speed up task completion"
        "<br>"
        "Please refer to the API platform's documentation for settings, 0 = Automatic"
    )
    basic_settings_page_rpm_threshold_title: str = "Requests Per Minute Threshold"
    basic_settings_page_rpm_threshold_content: str = (
        "Maximum total number of tasks executed per minute, i.e., the <font color='darkgoldenrod'><b>RPM</b></font> threshold"
        "<br>"
        "Some platforms may limit the request rate"
        "<br>"
        "Please refer to the API platform's documentation for settings, 0 = unlimited"
    )
    basic_settings_page_token_threshold_title: str = "Task Line Limit"
    basic_settings_page_token_threshold_content: str = "Maximum lines per task (5-15 recommended, fewer lines = more stable)"
    basic_settings_page_request_timeout_title: str = "Request Timeout"
    basic_settings_page_request_timeout_content: str = (
        "The maximum time (seconds) to wait for the model's response when making a request"
        "<br>"
        "If no reply is received after the timeout, the task will be considered failed"
    )
    basic_settings_page_max_round_title: str = "Maximum Rounds"
    basic_settings_page_max_round_content: str = "After completing a round of tasks, failed tasks will be retried in a new round until all are completed or the round threshold is reached"

    # 专家设置
    expert_settings_page_preceding_lines_threshold: str = "Preceding Lines Threshold"
    expert_settings_page_preceding_lines_threshold_desc: str = "Maximum number of preceding lines to include as context for each translation task, disabled by default"
    expert_settings_page_preceding_disable_on_local: str = "Enable Preceding Lines for Local Interface"
    expert_settings_page_preceding_disable_on_local_desc: str = "Local models perform relatively poorly, so the preceding Lines feature often has negative effects, disabled by default"
    expert_settings_page_single_line_translation: str = "Single-Line Translation Mode"
    expert_settings_page_single_line_translation_desc: str = (
        "When enabled, each request sends only one source line and accepts plain translated text as fallback"
        "<br>"
        "Useful for fast small models such as Tencent hy1.5 that often misalign batch JSONLINE output; this increases request count but reduces line-count mismatches"
    )
    expert_settings_page_structured_output: str = "Structured Output"
    expert_settings_page_structured_output_desc: str = (
        "When enabled, uses API-level JSON format enforcement (response_format) to guarantee valid output structure"
        "<br>"
        "Reduces parsing failures for capable models; disable as fallback if your API provider does not support it"
    )
    expert_settings_page_clean_ruby: str = "Clean Ruby Text"
    expert_settings_page_clean_ruby_desc: str = (
        "Removes the phonetic ruby characters from annotations, retaining only the main text, enabled by default"
        "<br>"
        "Ruby annotations in text are often not correctly understood by the model, cleaning them can improve translation quality"
        "<br>"
        "Supported ruby formats include, but are not limited to:"
        "<br>"
        "• (漢字/かんじ) [漢字/かんじ] |漢字[かんじ]"
        "<br>"
        "• \\r[漢字,かんじ] \\rb[漢字,かんじ] [r_かんじ][ch_漢字] [ch_漢字]"
        "<br>"
        "• [ruby text=かんじ] [ruby text = かんじ] [ruby text=\"かんじ\"] [ruby text = \"かんじ\"]"
    )
    expert_settings_page_deduplication_in_trans: str = "Deduplicate Repeated Text in T++ Project File"
    expert_settings_page_deduplication_in_trans_desc: str = "In T++ project file (i.e., <font color='darkgoldenrod'><b>.trans</b></font> file), whether to deduplicate repeated text, enabled by default"
    expert_settings_page_deduplication_in_bilingual: str = "Output Only Once if Source and Target are Identical in Bilingual Output Files"
    expert_settings_page_deduplication_in_bilingual_desc: str = "In subtitles or e-books, whether to output text only once if the source and target text are identical, enabled by default"
    expert_settings_page_write_translated_name_fields_to_file: str = "Write Translated Name Fields to the Output File"
    expert_settings_page_write_translated_name_fields_to_file_desc: str = (
        "In some <font color='darkgoldenrod'><b>GalGame</b></font>, name field data is bound to resource files such as image or voice files"
        "<br>"
        "Translating these name fields can cause errors. In such cases, this feature can be disabled, enabled by default"
        "<br>"
        "Supported formats:"
        "<br>"
        "• RenPy exported game text (.rpy)"
        "<br>"
        "• VNTextPatch or SExtractor exported game text with name fields (.json)"
    )
    expert_settings_page_auto_process_prefix_suffix_preserved_text: str = "Auto Process Prefix/Suffix Preserved Text"
    expert_settings_page_auto_process_prefix_suffix_preserved_text_desc: str = (
        "Whether to automatically handle prefix/suffix segments that match text preserve rules for each entry, enabled by default"
        "<br>"
        "• When enabled, preserved text at the beginning/end will be removed and reattached after translation"
        "<br>"
        "• When disabled, full text is sent to the model, which may preserve semantics but weakens text preservation"
    )
    expert_settings_page_honorific_placeholder_bridge: str = "Honorific Placeholder Smart Bridge"
    expert_settings_page_honorific_placeholder_bridge_desc: str = (
        "Automatically handles honorific + variable patterns (e.g., Mr.[xx]) to avoid placeholder loss and fix Chinese word order, enabled by default"
        "<br>"
        "• Before translation, placeholders are temporarily replaced with structured tokens to prevent variable translation or rewriting"
        "<br>"
        "• After translation, aliases are restored to original placeholders (e.g., [xx]先生), no manual glossary/search-replace needed"
    )
    expert_settings_page_honorific_placeholder_titles: str = "Honorific Title List (Customizable)"
    expert_settings_page_honorific_placeholder_titles_desc: str = (
        "Title words used to detect “honorific + placeholder” patterns; edit them directly in the table below and save to apply immediately"
    )
    expert_settings_page_honorific_placeholder_titles_placeholder: str = "Example: mr,mrs,dr,professor,master,captain,lord,sensei"
    expert_settings_page_honorific_placeholder_titles_column: str = "Title"
    expert_settings_page_honorific_placeholder_titles_select_delete: str = "Please select a row to delete"
    expert_settings_page_honorific_placeholder_titles_reload_success: str = "Honorific titles reloaded from config"
    expert_settings_page_honorific_placeholder_titles_save_success: str = "Saved {COUNT} honorific titles"
    expert_settings_page_sakura_jsonline_retry_enable: str = "Sakura JSONLINE Retry on Parse Failure"
    expert_settings_page_sakura_jsonline_retry_enable_desc: str = (
        "When SakuraLLM output is not JSONLINE, automatically send a formatting retry to improve pass rate"
    )
    expert_settings_page_result_checker_retry_count_threshold: str = "Result Checker - Retry Count Reached Threshold"
    expert_settings_page_result_checker_retry_count_threshold_desc: str = (
        "Include a list of items that <font color='darkgoldenrod'><b>reached the retry threshold</b></font> in the result check report, disabled by default"
        "<br>"
        "• After the retry threshold is reached, some checks are relaxed, but obvious failures such as copied source text or empty translations still do not pass directly"
        "<br>"
        "• This feature allows you to individually verify whether the final result of these items is actually reliable"
    )

    # 质量类通用
    quality_import: str = "Import"
    quality_import_toast: str = "Data imported …"
    quality_export: str = "Export"
    quality_export_toast: str = "Data exported to application root directory …"
    quality_save: str = "Save"
    quality_save_toast: str = "Data saved …"
    quality_merge_duplication: str = "Duplicate data merged …"
    quality_preset: str = "Preset"
    quality_reset: str = "Reset"
    quality_reset_toast: str = "Data reset …"
    quality_reset_alert: str = "Confirm reset to default data … ?"
    quality_select_file: str = "Select File"
    quality_select_file_type: str = "Support Format (*.json *.xlsx)"
    quality_delete_row: str = "Delete Row"
    quality_switch_regex: str = "Regex Switch"

    # Rule Column
    rule_regex: str = "Regular Expression"
    rule_regex_on: str = "Current Status: Enabled"
    rule_regex_off: str = "Current Status: Disabled"
    rule_case_sensitive: str = "Case Sensitive"
    rule_case_sensitive_on: str = "Current Status: Enabled"
    rule_case_sensitive_off: str = "Current Status: Disabled"

    # 术语表
    glossary_page_head_title: str = "Glossary"
    glossary_page_head_content: str = "By building a glossary in the prompt to guide model translation, unified translation and correction of personal pronouns can be achieved"
    glossary_page_table_row_01: str = "Original"
    glossary_page_table_row_02: str = "Translated"
    glossary_page_table_row_03: str = "Description"
    glossary_page_kg: str = "One-Click Tools"

    # 文本保护
    text_preserve_page_head_title: str = "Custom Text Preserve Rules"
    text_preserve_page_head_content: str = (
        "Preserve text segments like code snippets, control characters, and style characters that shouldn't be translated, preventing incorrect translation"
        "<br>"
        "<font color='darkgoldenrod'><b>Disabled by default</b></font>, before enabling, please carefully read the feature description in the <font color='darkgoldenrod'><b>Wiki</b></font> to ensure you fully understand how to use it"
        "<br>"
        "• Enabled - Preserve text by matching it against the <font color='darkgoldenrod'><b>Regular Expression Rules</b></font> set on this page"
        "<br>"
        "• Disabled - Automatically detects text format and game engine, and applies smart preserve rules, works well for most content"
    )
    text_preserve_page_table_row_01: str = "Rule"
    text_preserve_page_table_row_02: str = "Remarks (For reference only, has no actual effect)"

    # 译前替换
    pre_translation_replacement_page_head_title: str = "Pre-translation Replacement"
    pre_translation_replacement_page_head_content: str = (
        "Before translation, matched parts of the original text will be replaced by specified text, processed in top-down order"
        "<br>"
        "For <font color='darkgoldenrod'><b>RPGMaker MV/MZ</b></font> engine games:"
        "<br>"
        "• Importing <font color='darkgoldenrod'><b>actors.json</b></font> from <font color='darkgoldenrod'><b>data</b></font> or <font color='darkgoldenrod'><b>www\\data</b></font> in the game directory can improve translation quality"
        "<br>"
        "• Special handling is needed for games with custom names. Click the bottom-right button to see <font color='darkgoldenrod'><b>Wiki</b></font> instructions"
    )
    pre_translation_replacement_page_table_row_01: str = "Original"
    pre_translation_replacement_page_table_row_02: str = "Replacement"
    pre_translation_replacement_page_table_row_03: str = "Regex"

    # 译后替换
    post_translation_replacement_page_head_title: str = "Post-translation Replacement"
    post_translation_replacement_page_head_content: str = "After translation is completed, replace the matched parts in the translated text with the specified text, the execution order is from top to bottom"
    post_translation_replacement_page_table_row_01: str = "Original"
    post_translation_replacement_page_table_row_02: str = "Replacement"
    post_translation_replacement_page_table_row_03: str = "Regex"

    # 自定义提示词 - 中文
    custom_prompt_zh_page_head: str = "Custom Chinese Prompts (SakuraLLM model not supported)"
    custom_prompt_zh_page_head_desc: str = (
        "Add extra translation requirements such as story settings and writing styles via custom prompts"
        "<br>"
        "Note: The prefix and suffix are fixed and cannot be modified"
        "<br>"
        "The custom prompts on this page will only be used when the <font color='darkgoldenrod'><b>translation language is set to Chinese</b></font>"
    )

    # 自定义提示词 - 英文
    custom_prompt_en_page_head: str = "Custom English Prompts (SakuraLLM model not supported)"
    custom_prompt_en_page_head_desc: str = (
        "Add extra translation requirements such as story settings and writing styles via custom prompts"
        "<br>"
        "Note: The prefix and suffix are fixed and cannot be modified"
        "<br>"
        "The custom prompts on this page will only be used when the <font color='darkgoldenrod'><b>translation language is set to non-Chinese</b></font>"
    )

    # Translation prompt pipeline
    translation_prompt_mode_title: str = "Base Prompt Mode"
    translation_prompt_mode_desc: str = "Uses one base mode at a time; CUSTOM replaces only the base prompt and keeps the fixed engineering protocol"
    translation_prompt_mode_common: str = "General (COMMON)"
    translation_prompt_mode_cot: str = "Step-by-step (COT)"
    translation_prompt_mode_think: str = "Deep reasoning (THINK)"
    translation_prompt_mode_local: str = "Local model (LOCAL)"
    translation_prompt_mode_custom: str = "Custom (CUSTOM)"
    translation_custom_prompt_zh_title: str = "Chinese Base Prompt"
    translation_custom_prompt_zh_desc: str = "Used for a Chinese target language and replaces the selected base prompt"
    translation_custom_prompt_zh_placeholder: str = "Enter the Chinese base prompt"
    translation_custom_prompt_en_title: str = "English Base Prompt"
    translation_custom_prompt_en_desc: str = "Used for non-Chinese target languages and replaces the selected base prompt"
    translation_custom_prompt_en_placeholder: str = "Enter the English base prompt"
    translation_writing_style_title: str = "Writing Style"
    translation_writing_style_desc: str = "Appended independently and can be combined with any base prompt mode"
    translation_writing_style_none: str = "None (NONE)"
    translation_writing_style_literary: str = "Literary (LITERARY)"
    translation_writing_style_classical: str = "Classical (CLASSICAL)"
    translation_writing_style_r18: str = "Adult content (R18)"
    translation_writing_style_custom: str = "Custom (CUSTOM)"
    translation_custom_writing_style_title: str = "Custom Writing Style"
    translation_custom_writing_style_desc: str = "Appended as an independent style requirement without replacing the base prompt"
    translation_custom_writing_style_placeholder: str = "Enter custom writing-style requirements"
    translation_prompt_preview_action: str = "View Current Prompt"
    translation_prompt_preview_tooltip: str = "View the static prompt content used by the current configuration"
    translation_prompt_preview_title: str = "Current Prompt"
    translation_prompt_preview_base: str = "Base Prompt"
    translation_prompt_preview_style: str = "Writing Style"
    translation_prompt_preview_fixed: str = "Fixed Protocol"
    translation_prompt_preview_note: str = "Only static prompts from the current configuration are shown. Runtime worldbook, character cards, glossary, do-not-translate entries, and source text are not included."
    translation_prompt_preview_empty: str = "This section has no content"
    translation_prompt_preview_copy: str = "Copy Current Content"
    translation_prompt_preview_load_failed: str = "Failed to load the current prompt"
    translation_output_protocol_title: str = "Translation Output Protocol"
    translation_output_protocol_desc: str = "SINGLE_TEXT only permits one-item tasks and automatically enables single-line translation"
    translation_output_protocol_structured: str = "Structured JSON (STRUCTURED)"
    translation_output_protocol_jsonline: str = "Line-delimited JSON (JSONLINE)"
    translation_output_protocol_single_text: str = "Single plain text (SINGLE_TEXT)"
    translation_asset_regex_title: str = "Project Asset Regex Matching"
    translation_asset_regex_desc: str = "Matches glossary and do-not-translate entries explicitly marked as regex with regular expressions"
    translation_asset_token_budget_title: str = "Project Asset Token Budget"
    translation_asset_token_budget_desc: str = "Maximum dynamic project-asset tokens injected into each task"
    translation_asset_max_items_title: str = "Project Asset Item Limit"
    translation_asset_max_items_desc: str = "Maximum number of dynamic project-asset entries injected into each task"

    # 实验室
    laboratory_page_mtool_optimizer_enable: str = "MTool Optimizer"
    laboratory_page_mtool_optimizer_enable_desc: str = (
        "Can reduce translation time and token usage by up to 40% when translating MTool text"
        "<br>"
        "May lead to issues like <font color='darkgoldenrod'><b>residual original text</b></font> or <font color='darkgoldenrod'><b>incoherent sentences</b></font>"
        "<br>"
        "It should <font color='darkgoldenrod'><b>only be enabled when translating MTool text</b></font>"
        "<br>"
        "Please <font color='darkgoldenrod'><b>decide for yourself</b></font> whether to enable this feature"
        ""
        ""
    )
    laboratory_page_auto_glossary_enable: str = "Auto Complete Glossary (Does not support SakuraLLM)"
    laboratory_page_auto_glossary_enable_desc: str = (
        "Attempts to automatically add missing proper noun entries to the glossary during translation"
        "<br>"
        "This is effective only when the <font color='darkgoldenrod'><b>Glossary feature is enabled</b></font>"
        "<br>"
        "Designed to supplement, not replace, <font color='darkgoldenrod'><b>KeywordGacha</b></font>, acquired terms are <font color='darkgoldenrod'><b>written directly to the glossary</b></font>"
        "<br>"
        "May generate <font color='darkgoldenrod'><b>incorrect or inappropriate terminology entries</b></font>, please <font color='darkgoldenrod'><b>use your own judgment</b></font> on whether to enable it"
        "<br>"
        "It is recommended to use this feature only with powerful models like DeepSeek V3/R1"
    )

    # 百宝箱
    tool_box_page_batch_correction: str = "Batch Correction"
    tool_box_page_batch_correction_desc: str = "Checks the translated file against the generated translation results and performs batch correction on potential errors, enabling quick refinement of translation outputs"
    tool_box_page_re_translation: str = "Partial Re-Translation"
    tool_box_page_re_translation_desc: str = "Re-translate parts of already translated text based on set filters, mainly for content updates or error correction"
    tool_box_page_name_field_extraction: str = "Name-Field Extraction"
    tool_box_page_name_field_extraction_desc: str = (
        "Extract character name field data from <font color='darkgoldenrod'><b>RenPy</b></font> and <font color='darkgoldenrod'><b>GalGame</b></font> game text, "
        "and automatically generate corresponding glossary data to facilitate subsequent translation"
    )

    # 百宝箱 - 批量修正
    batch_correction_page: str = "Batch Correction"
    batch_correction_page_desc: str = (
        "Inspects data in files from translation results to batch correct potential errors, then generates corrected translation files"
        "<br>"
        "Workflow:"
        "<br>"
        "• Extracts data that may need correction from the translation result inspection file in the <font color='darkgoldenrod'><b>input folder</b></font>"
        "<br>"
        "• Checks the extracted data and corrects the entries that need correction according to the actual situation"
        "<br>"
        "• Inject the corrected data into the translated files within the <font color='darkgoldenrod'><b>Input folder</b></font>, and then generate the corrected translated files in the <font color='darkgoldenrod'><b>Output folder</b></font>"
    )
    batch_correction_page_step_01: str = "Step 1 - Generate Correction Data"
    batch_correction_page_step_01_desc: str = (
        "Extract data that may contain translation errors from the result check file"
        "<br>"
        f"Then automatically generate a data file for editing named <font color='darkgoldenrod'><b>{path_result_batch_correction}</b></font> in the <font color='darkgoldenrod'><b>Output Folder</b></font>"
    )
    batch_correction_page_step_02: str = "Step 2 - Inject Correction Data"
    batch_correction_page_step_02_desc: str = (
        "Check the content in the data file, and after confirming everything is correct, <font color='darkgoldenrod'><b>close</b></font> the file to start injection"
        "<br>"
        "Please note:"
        "<br>"
        "• Except for the <font color='darkgoldenrod'><b>correction column</b></font>, do not modify other data within the data file"
        "<br>"
        "• Filenames of some formats may contain language suffix like <font color='darkgoldenrod'><b>.zh</b></font>, remove it before injection for correct data matching"
    )
    batch_correction_page_title_01: str = "File Name"
    batch_correction_page_title_02: str = "Error Type"
    batch_correction_page_title_03: str = "Original Text (Do not modify this column)"
    batch_correction_page_title_04: str = "Translated Text (Do not modify this column)"
    batch_correction_page_title_05: str = "Correction (Please modify this column)"

    # 百宝箱 - 部分重翻
    re_translation_page: str = "Partial Re-Translation"
    re_translation_page_desc: str = (
        "Will filter the text in the <font color='darkgoldenrod'><b>Input Folder</b></font> based on the set filter conditions, and then retranslate the text that meets the conditions"
        "<br>"
        "Workflow:"
        "<br>"
        "• Load the original and translated texts from the <font color='darkgoldenrod'><b>src</b></font> and <font color='darkgoldenrod'><b>dst</b></font> subdirectories of the <font color='darkgoldenrod'><b>Input Folder</b></font>"
        "<br>"
        "• The filenames and file contents of the original and translated files must correspond strictly one-to-one"
        "<br>"
        "• Filter out the text that needs to be retranslated according to the settings on this page, translate it according to the normal process"
    )
    re_translation_page_white_list: str = "Keywords - Whitelist"
    re_translation_page_white_list_desc: str = (
        "Text containing these keywords will be retranslated. You can enter multiple keywords, one per line"
        "\n"
        "Hitting one of them is enough to determine that the text needs to be retranslated"
    )
    re_translation_page_alert_not_equal: str = "The number of lines in the original and translated texts does not match …"

    # 百宝箱 - 姓名字段提取
    name_field_extraction_page: str = "Name-Field Extraction"
    name_field_extraction_page_desc: str = (
        "Extract character name fields from all eligible files in the <font color='darkgoldenrod'><b>input folder</b></font> and automatically generate corresponding glossary data"
        "<br>"
        "Please note: This function <font color='darkgoldenrod'><b>cannot extract terms from the main text</b></font>, and cannot replace the <font color='darkgoldenrod'><b>KeywordGacha</b></font> tool"
        "<br>"
        "Supported formats:"
        "<br>"
        "• RenPy exported game text (.rpy)"
        "<br>"
        "• VNTextPatch or SExtractor exported game text with name fields (.json)"
    )
    name_field_extraction_page_step_01: str = "Step 1 - Extract Data"
    name_field_extraction_page_step_01_desc: str = (
        "Extract name fields and their related context, and send them to the translator for translation"
        "<br>"
        f"After translation is complete, the <font color='darkgoldenrod'><b>{path_result_name_field_extraction}</b></font> file will be generated in the <font color='darkgoldenrod'><b>Output Folder</b></font>"
    )
    name_field_extraction_page_step_02: str = "Step 2 - Generate Glossary"
    name_field_extraction_page_step_02_desc: str = (
        f"Extract translated data from the <font color='darkgoldenrod'><b>{path_result_name_field_extraction}</b></font> file in the <font color='darkgoldenrod'><b>Output Folder</b></font>"
        "<br>"
        "Then generate the corresponding glossary data, check if the generated glossary data is correct"
    )

    # 工具箱与工作台界面
    add_language_select_project_s_game_folder: str = "Select the project's game folder"
    add_language_adds_language_menu_so_players_can_switch: str = (
        'Adds a language menu so players can switch languages in the game settings.\n\nSteps:\n1. Se'
        "lect the project's game folder\n2. Click Add Language Menu\n3. The language-switching scri"
        'pt will be added automatically\n\nNote: This changes game scripts. Create a backup first.'
    )
    add_language_add_language_menu: str = 'Add Language Menu'
    add_language_select_game_folder: str = 'Select Game Folder'
    add_language_add_language_menu_2: str = '🌐 Add Language Menu'
    add_language_project_settings: str = '📁 Project Settings'
    add_language_game_folder: str = 'Game Folder:'
    add_language_about_tool: str = 'ℹ️ About This Tool'
    add_language_language_menu_script_added_hook_add_change: str = 'The language menu script was added (hook_add_change_language_entrance.rpy)'
    add_language_select_game_folder_2: str = 'Select the game folder'
    add_language_folder_does_not_exist: str = 'The folder does not exist'
    add_language_hook_file_missing: str = 'Hook file is missing: {hook_source}'
    add_language_failed_add_language_menu: str = 'Failed to add the language menu: {e}'
    android_build_android_shell_projects_download_modified_sdk_qq: str = 'For Android shell projects, download the modified SDK from QQ group 821152470.'
    android_build_select_renpy_sdk_folder: str = 'Select the renpy-sdk folder'
    android_build_select_ren_py_project_root_folder: str = "Select the Ren'Py project root folder"
    android_build_display_name: str = 'Display name'
    android_build_e_g_com_example_game: str = 'e.g. com.example.game'
    android_build_e_g_1_0_0: str = 'e.g. 1.0.0'
    android_build_automatically_update_java_code: str = 'Automatically Update Java Code'
    android_build_automatically_update_icons: str = 'Automatically Update Icons'
    android_build_icons_place_android_icon_foreground_png_android: str = (
        'Icons: place android-icon_foreground.png and android-icon_background.png in the project '
        'root (PNG, 1024x1024 recommended).\nSplash images: android-presplash.png/jpg and android-'
        'downloading.png/jpg (930x580 or the same aspect ratio recommended).'
    )
    android_build_signing_name: str = 'Signing Name:'
    android_build_organization_name_used_generate_keystore_optional: str = 'Organization or name used to generate the keystore (optional)'
    android_build_write_android_json: str = 'Write android.json'
    android_build_check_environment: str = 'Check Environment'
    android_build_install_sdk: str = 'Install SDK'
    android_build_generate_signing_key: str = 'Generate Signing Key'
    android_build_generates_apk_only_opens_rapt_bin_when: str = 'Generates an APK only. Opens rapt/bin when the build completes.'
    android_build_start_build: str = 'Start Build'
    android_build_open_rapt_bin: str = 'Open rapt/bin'
    android_build_separate_multiple_folders_semicolons_new_lines_leave: str = 'Separate multiple folders with semicolons or new lines; leave blank to use game'
    android_build_add: str = 'Add'
    android_build_detect: str = 'Detect'
    android_build_back_up_package_folders_zip_file_project: str = 'Back up package folders to a ZIP file in the project root'
    android_build_separate_folders_commas_semicolons_leave_blank_delete: str = 'Separate folders with commas or semicolons; leave blank to delete nothing (default: {default_dirs})'
    android_build_separate_folders_commas_semicolons_leave_blank_delete_2: str = 'Separate folders with commas or semicolons; leave blank to delete nothing'
    android_build_generate_archive_rpa_clean_resources: str = 'Generate archive.rpa + Clean Resources'
    android_build_select_ren_py_sdk_folder: str = "Select the Ren'Py SDK Folder"
    android_build_select_ren_py_project_folder: str = "Select the Ren'Py Project Folder"
    android_build_select_package_folder: str = 'Select a Package Folder'
    android_build_done: str = 'Done'
    android_build_detected_folder_s_replaced_current_list: str = 'Detected {detected_count} folder(s) and replaced the current list.'
    android_build_android_json_updated: str = 'android.json was updated.'
    android_build_checking_environment: str = 'Checking environment...'
    android_build_installing_sdk: str = 'Installing SDK...'
    android_build_generating_signing_key: str = 'Generating signing key...'
    android_build_building: str = 'Building...'
    android_build_processing_shell_package: str = 'Processing shell package...'
    android_build_shell_package_completed: str = 'Shell package completed.'
    android_build_archive_rpa_created: str = 'archive.rpa was created.'
    android_build_android_build: str = 'Android Build'
    android_build_paths: str = 'Paths'
    android_build_project_folder: str = 'Project Folder:'
    android_build_android_configuration_android_json: str = 'Android Configuration (android.json)'
    android_build_app_name: str = 'App Name:'
    android_build_package_name: str = 'Package Name:'
    android_build_version: str = 'Version:'
    android_build_environment_signing: str = 'Environment and Signing'
    android_build_build: str = 'Build'
    android_build_shell_package: str = 'Shell Package'
    android_build_pack_selected_folders_archive_rpa_project_root: str = 'Pack selected folders into archive.rpa in the project root, then clean large resource folders.'
    android_build_package_folders: str = 'Package Folders:'
    android_build_cleanup_folders: str = 'Cleanup Folders:'
    android_build_select_ren_py_sdk_folder_first: str = "Select the Ren'Py SDK folder first."
    android_build_select_project_folder_first: str = 'Select the project folder first.'
    android_build_project_folder_does_not_exist: str = 'Project folder does not exist: {project_dir}'
    android_build_game_folder_not_found: str = 'Game folder not found: {game_dir}'
    android_build_no_resource_folders_detected_field_cleared: str = 'No resource folders were detected; the field was cleared.'
    android_build_enter_app_name_package_name_version: str = 'Enter the app name, package name, and version.'
    android_build_no_signing_key_found_generate_one_first: str = 'No signing key was found. Generate one first.'
    android_build_build_completed: str = 'Build completed.'
    android_build_no_files_found_package: str = 'No files were found to package.'
    android_build_rapt_bin_not_found_run_build_first: str = 'rapt/bin was not found. Run a build first.'
    android_build_task_already_running: str = 'A task is already running.'
    android_build_failed: str = 'Failed'
    android_build_failed_create_distribution_folder: str = 'Failed to create the distribution folder.'
    android_build_build_failed: str = 'Build failed.'
    android_build_confirm_shell_processing: str = 'Confirm Shell Processing'
    android_build_build_archive_rpa_project_root_clean_configured: str = (
        'This will build archive.rpa in the project root and clean the configured resource folder'
        's.\nThe operation modifies project files. Back up the project first.'
    )
    android_build_package_folder_does_not_exist: str = 'Package folder does not exist: {source_dir}'
    android_build_package_path_not_folder: str = 'Package path is not a folder: {source_dir}'
    android_build_task_completed: str = 'Task completed.'
    android_build_task_failed: str = 'Task failed.'
    android_build_backup_failed: str = 'Backup failed: {exc}'
    direct_rpy_translate_tl_rpy_files_engine_workflow: str = '📄 Translate tl/.rpy Files (Engine Workflow)'
    direct_rpy_select_game_exe_project_folder: str = 'Select a game exe or project folder'
    direct_rpy_optional_defaults_game_tl_language: str = 'Optional; defaults to game/tl/<language>'
    direct_rpy_create_bak_backup_before_writing: str = 'Create a .bak Backup Before Writing'
    direct_rpy_start_translation: str = 'Start Translation'
    direct_rpy_select_game_exe_folder: str = 'Select Game exe or Folder'
    direct_rpy_executable_exe_all_files: str = 'Executable (*.exe);;All Files (*)'
    direct_rpy_select_tl_folder: str = 'Select tl Folder'
    direct_rpy_requesting_stop: str = 'Requesting stop...'
    direct_rpy_translating: str = 'Translating... {current}/{total}'
    direct_rpy_translation_complete: str = 'Translation Complete'
    direct_rpy_engine_translation_complete: str = 'Engine translation is complete'
    direct_rpy_stopped: str = 'Stopped'
    direct_rpy_path_settings: str = '📁 Path Settings'
    direct_rpy_game_file_folder: str = 'Game File or Folder:'
    direct_rpy_tl_folder: str = 'tl Folder:'
    direct_rpy_tl_language_folder_name: str = 'tl Language Folder Name:'
    direct_rpy_target_language: str = 'Target Language:'
    direct_rpy_simplified_chinese: str = 'Simplified Chinese'
    direct_rpy_traditional_chinese: str = 'Traditional Chinese'
    direct_rpy_english: str = 'English'
    direct_rpy_japanese: str = 'Japanese'
    direct_rpy_korean: str = 'Korean'
    direct_rpy_translation_has_been_sent_engine_please_wait: str = 'Translation was submitted to the engine. Please wait...'
    direct_rpy_started: str = 'Started'
    direct_rpy_unified_engine_workflow_has_started_progress_appears: str = 'The unified Engine workflow has started. Progress appears below.'
    direct_rpy_could_not_resolve_ren_py_project_paths: str = "Could not resolve the Ren'Py project paths"
    direct_rpy_tl_folder_does_not_exist: str = 'The tl folder does not exist: {tl_dir}'
    direct_rpy_tl_folder_does_not_exist_2: str = 'The tl/{tl_name} folder does not exist: {input_tl_dir}'
    direct_rpy_select_game_file_tl_folder_first: str = 'Select a game file or tl folder first'
    direct_rpy_tl_folder_not_found_run_extraction_select: str = 'The tl/{tl_name} folder was not found. Run extraction or select the tl folder.'
    extract_json_text_extraction_json: str = 'Text Extraction JSON'
    extract_json_complete_json_workflow_extract_export_json_translate: str = 'Complete JSON workflow: extract, export JSON, translate, import, and apply to tl'
    extract_json_select_game_executable_exe: str = 'Select the game executable (.exe)'
    extract_json_preview_file_count: str = 'Preview File Count'
    extract_json_extract_export_json: str = 'Extract & Export JSON'
    extract_json_exported_json_stores_all_rpy_text_one: str = 'The exported JSON stores all .rpy text in one file, grouped by source file path.'
    extract_json_json_import_export: str = 'JSON Import / Export'
    extract_json_import_json_apply_tl: str = 'Import JSON & Apply to tl'
    extract_json_translate_exported_json_then_import_tl_folder: str = (
        'Translate the exported JSON, then import it into the tl folder. Structure: {"translation'
        's": {file: [...]}}.'
    )
    extract_json_clean_tl_duplicates_empty_lines: str = 'Clean tl Duplicates & Empty Lines'
    extract_json_export_tl_json: str = 'Export tl to JSON'
    extract_json_select_ren_py_game_executable: str = "Select Ren'Py Game Executable"
    extract_json_executable_files_exe: str = 'Executable Files (*.exe)'
    extract_json_counting_files_text_entries: str = 'Counting files and text entries...'
    extract_json_export_json_file: str = 'Export JSON File'
    extract_json_json_files_json: str = 'JSON Files (*.json)'
    extract_json_extracting_text_generating_json: str = 'Extracting text and generating JSON...'
    extract_json_select_json_file: str = 'Select JSON File'
    extract_json_game_file: str = 'Game File:'
    extract_json_tl_language: str = 'tl Language:'
    extract_json_select_game_file: str = 'Select a game file'
    extract_json_game_file_does_not_exist: str = 'The game file does not exist'
    extract_json_preview_results: str = 'Preview Results'
    extract_json_found_text_entries_files_tl_all_entries: str = (
        'Found {total_entries} text entries in {total_files} files (tl/{tl_name}).\nAll entries wi'
        'll be written to one JSON file and grouped by source filename.'
    )
    extract_json_game_directory_not_found_select_correct_project: str = 'The game/ directory was not found. Select the correct project.'
    extract_json_importing_translations_json: str = 'Importing translations from JSON...'
    extract_json_tl_cleanup_complete: str = 'tl cleanup is complete'
    extract_json_select_export_path: str = 'Select Export Path'
    extract_json_failed_count_entries: str = 'Failed to count entries: {e}'
    extract_json_success: str = 'Success'
    extract_json_json_export_completed_tl_all_entries_written: str = (
        'JSON export completed (tl/{tl_name}).\nAll entries were written to one file and grouped b'
        'y source filename.'
    )
    extract_json_no_text_extracted_export_skipped: str = 'No text was extracted, or the export was skipped'
    extract_json_export_failed: str = 'Export failed: {e}'
    extract_json_no_usable_translation_entries_found_json_file: str = 'No usable translation entries were found in the JSON file'
    extract_json_applied_tl_processed_translations_files: str = (
        'Applied to tl/{target_lang}.\nProcessed {total_entries} translations in {total_files} fil'
        'es.'
    )
    extract_json_failed_apply_translations: str = 'Failed to apply translations'
    extract_json_import_failed: str = 'Import failed: {e}'
    extract_json_tl_folder_not_found: str = 'The tl folder was not found: {tl_dir}'
    extract_json_tl_cleanup_failed: str = 'TL cleanup failed: {e}'
    extract_json_tl_export_completed_translations_files_written_one: str = (
        'TL export completed.\n{total_entries} translations from {total_files} files were written '
        'to one JSON file.\nSkipped {skipped} resource or placeholder entries.'
    )
    extract_json_tl_export_failed: str = 'TL export failed'
    extract_json_tl_export_failed_2: str = 'TL export failed: {e}'
    font_replace_if_game_cannot_display_translated_text_font: str = (
        '💡 If the game cannot display Chinese text, its font usually lacks the required glyphs.\n'
        'This tool injects the bundled Chinese font pack into the tl folder without modifying original files.\n'
        'Select the game folder, then click Inject Fonts.'
    )
    font_replace_select_project_root_game_folder: str = 'Select the project root or game folder'
    font_replace_select_game_folder_first: str = 'Select the game folder first.'
    font_replace_auto_detect: str = 'Auto Detect'
    font_replace_select_translation_language_receive_font_pack_chinese: str = (
        'Select the translation language that will receive the font pack. For Chinese translation'
        's, choose chinese.'
    )
    font_replace_inject_fonts: str = '✨ Inject Fonts'
    font_replace_expand: str = 'Expand'
    font_replace_leave_blank_use_bundled_font: str = 'Leave blank to use the bundled font'
    font_replace_not_scanned: str = 'Not Scanned'
    font_replace_only_fonts_referenced_scripts_listed_here_unreferenced: str = (
        'Only fonts referenced by scripts are listed here. Unreferenced files under game/fonts ar'
        'e counted separately.'
    )
    font_replace_replace_all_detected_fonts: str = 'Replace All Detected Fonts'
    font_replace_leave_blank_replace_all_detected_fonts: str = 'Leave blank to replace all detected fonts'
    font_replace_also_generate_gui_font_hook_optional: str = 'Also Generate a GUI Font Hook (Optional)'
    font_replace_creates_font_hook_tl_lang_gui_rpy: str = 'Creates a font hook in tl/<lang>/gui.rpy for compatibility with older projects'
    font_replace_automatically_back_up_before_replacing_recommended: str = 'Automatically Back Up Before Replacing (Recommended)'
    font_replace_scan_all_fonts: str = 'Scan All Fonts'
    font_replace_replace_all_fonts: str = 'Replace All Fonts'
    font_replace_select_game_folder: str = 'Select the Game Folder'
    font_replace_select_font_file: str = 'Select a Font File'
    font_replace_font_files_ttf_otf_all_files: str = 'Font Files (*.ttf *.otf);;All Files (*)'
    font_replace_game_folder_rescanned: str = 'The game folder was rescanned.'
    font_replace_font_injection: str = '🔤 Font Injection'
    font_replace_select_game_folder_2: str = '📁 Select Game Folder'
    font_replace_advanced_options: str = '⚙️ Advanced Options'
    font_replace_custom_font: str = 'Custom Font:'
    font_replace_detected_font_references: str = 'Detected Font References:'
    font_replace_original_font: str = 'Original Font:'
    font_replace_collapse: str = 'Collapse'
    font_replace_default_language_global_replacement: str = 'Default Language (Global Replacement)'
    font_replace_scan_complete_font_reference_s_font_file: str = (
        '✅ Scan complete: {font_count} font reference(s), {font_file_count} font file(s), and {la'
        'ng_count} translation language(s) found'
    )
    font_replace_scripts_reference_font_s_font_file_s: str = (
        'Scripts reference {font_count} font(s); {font_file_count} font file(s) were found under '
        'game/fonts, game/gui, and related folders. Replace All Detected Fonts only changes fonts'
        ' referenced by scripts.'
    )
    font_replace_replacing_fonts_please_wait: str = 'Replacing fonts. Please wait...'
    font_replace_font_replacement_complete_file_s_replacement_s: str = 'Font replacement complete: {replaced_files} file(s), {replaced_count} replacement(s)'
    font_replace_backup_fonts_backup: str = (
        '\nBackup: fonts_backup/{details_backup_name}'
    )
    font_replace_font_replacement_failed: str = 'Font replacement failed: {message}'
    font_replace_font_replacement_failed_2: str = 'Font replacement failed: {message}'
    font_replace_folder_does_not_exist: str = '❌ The folder does not exist.'
    font_replace_scan_failed: str = '❌ Scan failed: {e}'
    font_replace_folder_does_not_exist_2: str = 'The folder does not exist.'
    font_replace_font_injection_failed: str = 'Font injection failed: {message}'
    font_replace_font_injection_failed_2: str = 'Font injection failed: {e}'
    font_replace_font_replacement_failed_3: str = 'Font replacement failed: {e}'
    font_replace_no_font_references_detected_font_file_s: str = 'No font references detected ({discovered_font_files_count} font file(s) found)'
    font_replace_no_font_references_detected: str = 'No Font References Detected'
    font_replace_font_pack_injected_but_gui_hook_could: str = 'The font pack was injected, but the GUI hook could not be generated.'
    font_replace_custom_font_file_does_not_exist: str = 'The custom font file does not exist.'
    font_replace_bundled_font_not_found: str = 'The bundled font was not found.'
    font_replace_select_replace_all_detected_fonts_enter_original: str = 'Select Replace All Detected Fonts or enter an original font.'
    font_replace_no_font_references_detected_2: str = 'No font references were detected.'
    local_glossary_added_candidates_updated_existing_entries_scanned_text: str = (
        'Added {added_count} candidates, updated {updated_count} existing entries, and scanned {c'
        'orpus_count} text samples.'
    )
    local_glossary_category: str = 'Category'
    local_glossary_notes: str = 'Notes'
    local_glossary_hits: str = 'Hits'
    local_glossary_project_glossary: str = '📚 Project Glossary'
    local_glossary_import_glossary_entries_excel_confirm_save_them: str = (
        'Import glossary entries from Excel, confirm and save them to the current project, or exp'
        'ort them for sharing.'
    )
    local_glossary_project_data: str = 'Project Data'
    local_glossary_import_excel: str = 'Import Excel'
    local_glossary_export_excel: str = 'Export Excel'
    local_glossary_save_project: str = 'Save to Project'
    local_glossary_load_project: str = 'Load from Project'
    local_glossary_count_hits: str = 'Count Hits'
    local_glossary_count_how_many_cached_output_entries_contain: str = 'Count how many cached output entries contain each glossary term.'
    local_glossary_table_actions: str = 'Table Actions'
    local_glossary_deduplicate: str = 'Deduplicate'
    local_glossary_deduplicate_source_text_while_preserving_existing_translations: str = 'Deduplicate by source text while preserving existing translations, categories, and notes.'
    local_glossary_add_entry: str = 'Add Entry'
    local_glossary_confirm_selected: str = 'Confirm Selected'
    local_glossary_mark_selected_candidates_confirmed_only_confirmed_candidates: str = (
        'Mark selected candidates as confirmed. Only confirmed candidates with translations becom'
        'e glossary entries when saved.'
    )
    local_glossary_delete_selected: str = 'Delete Selected'
    local_glossary_clear_all: str = 'Clear All'
    local_glossary_delete_all_glossary_entries_loaded_candidates_current: str = 'Delete all glossary entries and loaded candidates from the current project.'
    local_glossary_auto_categorize: str = 'Auto Categorize'
    local_glossary_use_ner_first_when_available_then_fill: str = 'Use NER first when available, then fill blank categories with keyword rules.'
    local_glossary_scan_translate: str = 'Scan and Translate'
    local_glossary_scan_term_candidates: str = 'Scan Term Candidates'
    local_glossary_scan_game_scripts_proper_noun_candidates_configured: str = 'Scan game scripts for proper-noun candidates. A configured LLM can improve recall.'
    local_glossary_stop_scan: str = 'Stop Scan'
    local_glossary_request_current_candidate_scan_stop_after_any: str = 'Request the current candidate scan to stop after any in-flight LLM batch finishes.'
    local_glossary_scan_character_names: str = 'Scan Character Names'
    local_glossary_scan_game_folder_character_names_replace_previous: str = 'Scan the game folder for character names and replace previous auto-extracted candidates.'
    local_glossary_translate_llm: str = 'Translate with LLM'
    local_glossary_use_configured_llm_api_fill_blank_placeholder: str = (
        'Use the configured LLM/API to fill blank or placeholder translations without overwriting'
        ' completed entries.'
    )
    local_glossary_fast_translation: str = 'Fast Translation'
    local_glossary_use_google_bing_faster_batch_translation_without: str = 'Use Google or Bing for faster batch translation without overwriting completed entries.'
    local_glossary_candidate_scan_has_not_started: str = 'Candidate scan has not started'
    local_glossary_glossary_entries_cells_editable: str = 'Glossary entries (cells are editable)'
    local_glossary_confirmed: str = 'Confirmed'
    local_glossary_confirmed_candidates_add_translations_then_save_them: str = 'Confirmed {confirmed} candidates. Add translations, then save them to the project.'
    local_glossary_cleared: str = 'Cleared'
    local_glossary_deleted_all_glossary_entries_loaded_candidates_current: str = 'Deleted all glossary entries and loaded candidates from the current project.'
    local_glossary_translation_started: str = 'Translation Started'
    local_glossary_translating_glossary_entries_llm: str = 'Translating {tasks_count} glossary entries with the LLM...'
    local_glossary_translating_glossary_entries: str = 'Translating {tasks_count} glossary entries...'
    local_glossary_preparing_term_candidate_scan: str = 'Preparing the term candidate scan...'
    local_glossary_scan_started: str = 'Scan Started'
    local_glossary_scanning_game_scripts_term_candidates: str = 'Scanning game scripts for term candidates...'
    local_glossary_stopping_term_candidate_scan: str = 'Stopping the term candidate scan...'
    local_glossary_scan_stop_after_current_batch_finishes: str = 'The scan will stop after the current batch finishes.'
    local_glossary_term_candidate_scan_stopped: str = 'Term candidate scan stopped'
    local_glossary_successful_llm_batches: str = ' Successful LLM batches: {llm_chunks_success}/{max_llm_chunks_total_llm_chunks_success}.'
    local_glossary_term_candidate_scan_completed: str = 'Term candidate scan completed'
    local_glossary_statistics_completed: str = 'Statistics Completed'
    local_glossary_analyzed_glossary_entries_across_cached_entries: str = 'Analyzed {counts_count} glossary entries across {counted_item_total} cached entries.'
    local_glossary_completed: str = 'Completed'
    local_glossary_loaded_glossary_entries_current_project_candidates_need: str = (
        'Loaded {converted_count} glossary entries from the current project; {candidate_count} ca'
        'ndidates need confirmation.'
    )
    local_glossary_saved: str = 'Saved'
    local_glossary_saved_confirmed_glossary_entries_kept_incomplete_candidates: str = 'Saved {formal_count} confirmed glossary entries and kept {candidate_count} incomplete candidates.'
    local_glossary_select_glossary_excel_file: str = 'Select Glossary Excel File'
    local_glossary_excel_files_xlsx: str = 'Excel Files (*.xlsx)'
    local_glossary_save_glossary_excel_file: str = 'Save Glossary Excel File'
    local_glossary_found_character_names_confirmation_removed_previous_auto: str = (
        'Found {new_entries_count} character names for confirmation and removed previous auto-ext'
        'racted candidates.'
    )
    local_glossary_translating_glossary: str = 'Translating glossary...'
    local_glossary_glossary_translation_completed: str = 'Glossary translation completed'
    local_glossary_translated_entries: str = 'Translated {results_count} entries'
    local_glossary_batch_entries: str = 'batch {batch_index}/{total_batches}, {srcs_count} entries'
    local_glossary_translated_entries_2: str = 'Translated {all_results_count} entries'
    local_glossary_select_entry_delete: str = 'Select an entry to delete.'
    local_glossary_select_one_more_candidates_confirm: str = 'Select one or more candidates to confirm.'
    local_glossary_selected_entries_not_pending_candidates_already_confirmed: str = 'The selected entries are not pending candidates or are already confirmed.'
    local_glossary_table_empty: str = 'The table is empty.'
    local_glossary_removed_duplicate_entries_kept: str = 'Removed {removed} duplicate entries and kept {deduped_count}.'
    local_glossary_no_duplicate_entries_found: str = 'No duplicate entries found.'
    local_glossary_glossary_translation_already_running: str = 'Glossary translation is already running.'
    local_glossary_there_no_entries_translate_translation_column_already: str = 'There are no entries to translate; the translation column is already filled.'
    local_glossary_no_translation_engine_available_configure_enable_platform: str = 'No translation engine is available. Configure and enable a platform first.'
    local_glossary_translation_failed: str = 'Translation Failed'
    local_glossary_translation_completed: str = 'Translation Completed'
    local_glossary_filled_translations_confirm_candidates_save_them_project: str = 'Filled {applied} translations. Confirm the candidates and save them to the project.'
    local_glossary_translation_finished_without_usable_results_service_may: str = 'Translation finished without usable results; the service may have returned the source text.'
    local_glossary_select_game_folder_containing_game_subfolder: str = 'Select the Game Folder (containing the game subfolder)'
    local_glossary_game_folder_does_not_exist: str = 'The game folder does not exist: {target_path}'
    local_glossary_term_candidate_scan_already_running: str = 'A term candidate scan is already running.'
    local_glossary_no_compatible_llm_available_scan_use_rules: str = 'No compatible LLM is available. The scan will use rules only.'
    local_glossary_no_term_candidate_scan_running: str = 'No term candidate scan is running.'
    local_glossary_term_candidate_scan_failed: str = 'Term candidate scan failed'
    local_glossary_scan_failed: str = 'Scan Failed'
    local_glossary_scan_result_has_invalid_format: str = 'The scan result has an invalid format.'
    local_glossary_scan_completed_without_usable_term_candidates: str = 'Scan completed without usable term candidates'
    local_glossary_scan_completed: str = 'Scan Completed'
    local_glossary_hit_statistics_already_running: str = 'Hit statistics are already running.'
    local_glossary_there_no_glossary_entries_analyze: str = 'There are no glossary entries to analyze.'
    local_glossary_statistics_failed: str = 'Statistics Failed'
    local_glossary_statistics_result_has_invalid_format: str = 'The statistics result has an invalid format.'
    local_glossary_statistics_result_does_not_contain_hit_counts: str = 'The statistics result does not contain hit counts.'
    local_glossary_glossary_changed_run_statistics_again: str = 'The glossary changed. Run the statistics again.'
    local_glossary_openpyxl_not_installed_so_excel_files_cannot: str = 'openpyxl is not installed, so Excel files cannot be imported.'
    local_glossary_imported: str = 'Imported'
    local_glossary_imported_glossary_entries: str = 'Imported {items_count} glossary entries.'
    local_glossary_openpyxl_not_installed_so_excel_files_cannot_2: str = 'openpyxl is not installed, so Excel files cannot be exported.'
    local_glossary_table_empty_no_file_exported: str = 'The table is empty; no file was exported.'
    local_glossary_exported: str = 'Exported'
    local_glossary_saved_2: str = 'Saved to {path}'
    local_glossary_game_folder_does_not_exist_2: str = 'The game folder does not exist: {game_path}'
    local_glossary_no_character_names_found_check_selected_game: str = 'No character names were found. Check the selected game folder.'
    local_glossary_ner_categorized_entries_keyword_rules_categorized: str = 'NER categorized {ner_count} entries and keyword rules categorized {kw_count}.'
    local_glossary_no_entries_could_categorized_check_model_source: str = 'No entries could be categorized. Check the model and source text.'
    local_glossary_no_entries_translate: str = 'No entries to translate'
    local_glossary_no_translation_engine_selected_configure_enable_platform: str = 'No translation engine is selected. Configure and enable a platform first.'
    local_glossary_translating_glossary_llm: str = 'Translating glossary with LLM... ({batch_label})'
    local_glossary_waiting_model: str = 'Waiting for the model... ({batch_label})'
    local_glossary_translated_glossary_entries: str = 'Translated {len_batch_total}/{total} glossary entries'
    local_glossary_game_folder_set: str = 'Game folder set to: {source_root}'
    local_glossary_select_game_folder_first: str = 'Select a game folder first.'
    local_glossary_active_platform_does_not_support_term_extraction: str = 'The active platform does not support term extraction. The scan will use rules only.'
    local_glossary_scan_completed_but_candidates_could_not_saved: str = 'Scan completed, but the candidates could not be saved'
    local_glossary_save_failed: str = 'Save Failed'
    local_glossary_candidates_displayed_but_could_not_saved_project: str = 'Candidates are displayed but could not be saved to the project cache: {exc}'
    local_glossary_source_translation_column_not_found_check_template: str = 'The Source or Translation column was not found. Check the template.'
    local_glossary_categorized_entries: str = 'Categorized {changed} entries.'
    local_glossary_no_blank_categories_could_matched: str = 'No blank categories could be matched.'
    local_glossary_no_ner_model_found_under_resource_models: str = 'No NER model was found under Resource/Models/ner; this step was skipped.'
    local_glossary_ner_categorized_entries: str = 'NER categorized {changed} entries.'
    local_glossary_no_entries_could_categorized: str = 'No entries could be categorized.'
    local_glossary_spacy_not_installed: str = 'spaCy is not installed: {e}'
    local_glossary_failed_load_ner_model: str = 'Failed to load the NER model: {e}'
    onekey_cleaning_incremental_folders: str = 'Cleaning the incremental folders...'
    onekey_restoring_translation_paths: str = 'Restoring translation paths...'
    onekey_applied_translation_files_game_folder_you_can: str = (
        'Applied {success_count} translation files to the game folder.\nYou can now start the game'
        ' and review the translation.'
    )
    onekey_step_5: str = 'Step {step}/5: {title}'
    onekey_select_game: str = 'Select Game'
    onekey_quick_start: str = '💡 Quick Start'
    onekey_1_select_game_folder_contains_game_subfolder: str = (
        '1. Select the game folder that contains the game subfolder.\n2. Click Extract Text to ext'
        'ract translatable text automatically.\n3. When extraction finishes, click Start Translati'
        'on.\n💬 Existing translations are preserved automatically.'
    )
    onekey_enter_paste_game_folder_path_example_d: str = 'Enter or paste a game folder path, for example: D:\\Games\\MyGame'
    onekey_browse: str = 'Browse...'
    onekey_existing_translation_detected: str = '🔍 Existing Translation Detected'
    onekey_game_already_has_translation_files_choose_how: str = 'This game already has translation files. Choose how to proceed:'
    onekey_incremental_extraction_recommended: str = 'Incremental extraction (recommended)'
    onekey_keep_existing_translations_extract_new_untranslated_entries: str = 'Keep existing translations and extract new or untranslated entries'
    onekey_full_extraction_start_over: str = 'Full extraction (start over)'
    onekey_backs_up_regenerates_tl_lang_existing_placeholders: str = 'Backs up and regenerates tl/<lang>. Existing placeholders are reset.'
    onekey_back_up_old_translation_extract_everything_again: str = 'Back up the old translation and extract everything again'
    onekey_tip_incremental_extraction_protects_existing_translations_use: str = (
        'Tip: Incremental extraction protects existing translations. Use full extraction only whe'
        'n starting over.'
    )
    onekey_merge_automatically_remove_duplicates_after_extraction: str = 'Merge automatically and remove duplicates after extraction'
    onekey_advanced_options: str = 'Advanced Options'
    onekey_inject_ui_translation_pack_base_box: str = 'Inject the UI translation pack (base_box)'
    onekey_injects_bundled_ui_translations_start_save_settings: str = (
        'Injects bundled UI translations for Start, Save, Settings, and more.\nDisable this option'
        ' if the game already has custom UI translations.'
    )
    onekey_review_untranslated_uppercase_abbreviations_uses_additional_quota: str = 'Review untranslated uppercase abbreviations (uses additional quota)'
    onekey_clear_skipped_candidates: str = 'Clear skipped candidates'
    onekey_click_extract_text_begin_existing_translations_preserved: str = 'Click Extract Text to begin. Existing translations are preserved by default.'
    onekey_skip_extraction_translate: str = 'Skip extraction and translate →'
    onekey_extract_text: str = 'Extract Text →'
    onekey_extract_text_2: str = 'Extract Text'
    onekey_ready_extract: str = 'Ready to extract...'
    onekey_text_extracted_game_translation_files_when_finishes: str = (
        'Text will be extracted from the game into translation files. When it finishes, start tra'
        'nslation or extract again.'
    )
    onekey_extract_again: str = 'Extract Again'
    onekey_project_changed_extract_again: str = 'The project changed. Extract it again.'
    onekey_open_rpa_unpacker: str = 'Open RPA Unpacker'
    onekey_skip_step: str = 'Skip This Step'
    onekey_next: str = 'Next →'
    onekey_merge_remove_duplicates: str = 'Merge and Remove Duplicates'
    onekey_clear_skipped_candidates_2: str = 'Clear Skipped Candidates'
    onekey_these_terms_translated_again_during_next_run: str = 'These terms will be retried for translation during the next run.'
    onekey_clear: str = 'Clear'
    onekey_terms_translation_context: str = 'Terms and Translation Context'
    onekey_looking_glossary_files_project: str = 'Looking for glossary files in the project...'
    onekey_open_local_glossary: str = '📂 Open Local Glossary'
    onekey_use_scan_term_candidates_local_glossary_find: str = 'Use Scan Term Candidates in Local Glossary to find proper names beyond character names.'
    onekey_open_do_not_translate_list: str = '🚫 Open Do Not Translate List'
    onekey_extract_character_names: str = '🔍 Extract Character Names'
    onekey_open_character_world_workbench: str = '🎭 Open Character & World Workbench'
    onekey_manage_worldbook_character_cards_translation_creates_immutable: str = 'Manage the worldbook and character cards. Translation creates an immutable context snapshot.'
    onekey_loading_project_assets: str = 'Loading project assets...'
    onekey_next_start_translation: str = 'Next (Start Translation) →'
    onekey_run_ai_translation: str = 'Run AI Translation'
    onekey_translation_files_written_separate_folder_under_game: str = (
        'Translation files are written to a separate folder under the game root, where the engine'
        ' will not load them.\nApply them to the game from Post-processing when translation is com'
        'plete.'
    )
    onekey_start_translation: str = '🚀 Start Translation'
    onekey_recover_missed_text_after_translation_replace_text: str = 'Recover missed text after translation (replace_text)'
    onekey_disabled_default_when_enabled_second_pass_generates: str = (
        'Disabled by default.\nWhen enabled, a second pass generates and translates replace_text_a'
        'uto.rpy after the main translation.'
    )
    onekey_skip_translation: str = 'Skip Translation →'
    onekey_review_export_post_process: str = 'Review, Export, and Post-process'
    onekey_apply_translation_5: str = 'Apply Translation'
    onekey_select_game_folder: str = 'Select Game Folder'
    onekey_no_extractable_files_found: str = 'No extractable files were found'
    onekey_extracting_text_game_creating_translation_files: str = 'Extracting text from the game and creating translation files...'
    onekey_checking_game_files: str = '🔍 Checking game files...'
    onekey_character_candidates_variable_references_scanned: str = 'Character candidates were sent to the workbench, and variable references to the do-not-translate list'
    onekey_translation_folders: str = '📁 Translation Folders'
    onekey_b_input_folder_b_files_translate_br: str = (
        "<b>Input folder</b> (files to translate):<br><code style='background:{code_bg};padding:2"
        "px 4px;'>{input_folder}</code><br><br><b>Output folder</b> (translation results):<br><co"
        "de style='background:{code_bg};padding:2px 4px;'>{output_folder}</code><br><br><p style="
        "'color:{hint_color};'><i>💡 The output folder is under the game root and is not loaded by"
        " Ren'Py.<br>Apply the translation from Post-processing when it is complete.</i></p>"
    )
    onekey_confirm_translation_application: str = 'Confirm Translation Application'
    onekey_b_apply_translation_game_b_br_br: str = (
        "<b>Apply translation to the game</b><br><br><b>Source folder:</b><br><code style='backgr"
        "ound:{code_bg};padding:2px 4px;'>{output_dir}</code><br><br><b>Target folder:</b><br><co"
        "de style='background:{code_bg};padding:2px 4px;'>{input_dir}</code><br><br><b>Files:</b>"
        " {output_files_count}<br><br><p style='color:{warn_color};'><i>⚠️ Files with the same na"
        'mes in the target folder will be overwritten.<br>Back up the original files first.</i></'
        'p>'
    )
    onekey_apply_translation: str = 'Apply Translation'
    onekey_applying_translation_game: str = 'Applying translation to the game...'
    onekey_translation_files_applied_but_cache_remains_try: str = (
        'The translation files were applied, but the cache remains at {self_output_dir_cache}. Tr'
        'y applying again later.'
    )
    onekey_back_toolbox: str = 'Back to Toolbox'
    onekey_previous_step: str = 'Previous step'
    onekey_exit_wizard: str = 'Exit Wizard'
    onekey_translation_languages: str = 'Translation Languages'
    onekey_source_language: str = 'Source language'
    onekey_russian: str = 'Russian'
    onekey_other: str = 'Other'
    onekey_target_language: str = 'Target language'
    onekey_tl_folder_name: str = 'TL folder name'
    onekey_existing_translation_detected_files: str = '🔍 Existing Translation Detected ({rpy_count} files)'
    onekey_translation_files_already_exist_tl_choose_how: str = 'Translation files already exist in tl/{tl_name}. Choose how to proceed:'
    onekey_select_valid_game_folder_first: str = 'Select a valid game folder first'
    onekey_could_not_locate_game_s_game_folder: str = "Could not locate the game's game folder"
    onekey_select_game_folder_first: str = 'Select a game folder first'
    onekey_cleared: str = 'Cleared'
    onekey_cleared_skipped_candidates: str = 'Cleared {cleared} skipped candidates'
    onekey_there_no_skipped_candidates: str = 'There are no skipped candidates'
    onekey_glossary_do_not_translate_list: str = 'Glossary and Do Not Translate List'
    onekey_glossary_keeps_proper_names_consistent_while_do: str = (
        'The glossary keeps proper names consistent, while the Do Not Translate list protects var'
        'iables and code. You can also scan for term candidates in Local Glossary.'
    )
    onekey_ready_translate: str = 'Ready to Translate'
    onekey_translation_complete: str = '🎉 Translation Complete'
    onekey_you_can_now_review_complete_export_translation: str = 'You can now review, complete, or export the translation.'
    onekey_if_text_still_untranslated_game_use_recover: str = 'If text is still untranslated in-game, use Recover Missed Text to generate replace_text_auto.rpy.'
    onekey_review_polish_export: str = 'Review, Polish, and Export'
    onekey_review_quality_reports_edit_selected_translations_export: str = 'Review quality reports, edit selected translations, and export the result'
    onekey_recover_missed_text: str = 'Recover Missed Text'
    onekey_find_text_missing_tl_generate_replace_text: str = 'Find text missing from TL and generate replace_text_auto.rpy'
    onekey_detect_repair_errors: str = 'Detect / Repair Errors'
    onekey_fix_indentation_formatting_issues: str = 'Fix indentation and formatting issues'
    onekey_set_default_language: str = 'Set Default Language'
    onekey_set_language_used_when_game_starts: str = 'Set the language used when the game starts'
    onekey_add_language_switch: str = 'Add Language Switch'
    onekey_inject_language_switching_button: str = 'Inject a language-switching button'
    onekey_inject_fonts: str = 'Inject Fonts'
    onekey_inject_bundled_font_pack: str = 'Inject a bundled font pack'
    onekey_open_game_folder: str = 'Open Game Folder'
    onekey_view_translation_results: str = 'View translation results'
    onekey_export_language_patch: str = 'Export Language Patch'
    onekey_export_tl_folder_zip_archive: str = 'Export the TL folder as a ZIP archive'
    onekey_open: str = 'Open {title}'
    onekey_game_folder_not_found: str = 'The game folder was not found'
    onekey_found_rpa_archives_must_unpacked: str = 'Found {rpa_count} RPA archives that must be unpacked'
    onekey_found_rpyc_files_must_decompiled: str = 'Found {rpyc_count} RPYC files that must be decompiled'
    onekey_found_rpy_files_rpyc_files: str = 'Found {rpy_count} RPY files and {rpyc_count} RPYC files'
    onekey_found_rpy_files_ready_extraction: str = 'Found {rpy_count} RPY files ready for extraction'
    onekey_decompilation_completed_unrpyc_v2: str = 'Decompilation completed (unrpyc v2)'
    onekey_extraction_already_running_wait_finish: str = 'Extraction is already running. Wait for it to finish.'
    onekey_decompiling_rpyc_files: str = '🔨 Decompiling RPYC files...'
    onekey_running_incremental_extraction: str = '🔄 Running incremental extraction...'
    onekey_extracting: str = 'Extracting...'
    onekey_extraction_complete: str = '✓ Extraction Complete'
    onekey_new_content_written_existing_translations_left_unchanged: str = (
        '{msg}\n\n💡 New content was written to {name}/.\nExisting translations were left unchanged.'
    )
    onekey_incremental_input_incremental_output: str = (
        '\nIncremental input: {name}/\nIncremental output: {name_2}/'
    )
    onekey_placeholders_preserved_new_old_you_can_translate: str = (
        '{msg}\nPlaceholders were preserved (new == old). You can translate now or update the glos'
        'sary and extract again.'
    )
    onekey_start_translation_2: str = 'Start Translation →'
    onekey_extraction_completed_character_names_variable_references_scanned: str = 'Extraction completed. Character names and variable references were scanned automatically.'
    onekey_extraction_failed: str = '✗ Extraction Failed'
    onekey_error_select_extract_again_if_still_fails: str = (
        'Error: {msg}\n\nSelect Extract Again. If it still fails, check the path and permissions or'
        ' skip directly to translation.'
    )
    onekey_extraction_failed_you_can_try_again_skip: str = 'Extraction failed. You can try again or skip this step.'
    onekey_found: str = 'Found: {join_found_files}'
    onekey_no_glossary_files_found_default_configuration_used: str = 'No glossary files were found. The default configuration will be used.'
    onekey_activate_translation_provider_configure_input_output_folders: str = 'Activate a translation provider and configure the input and output folders first.'
    onekey_main_translation_complete_recovering_missed_text: str = 'Main translation is complete. Recovering missed text...'
    onekey_translation_complete_continue_post_processing_apply_game: str = '✔ Translation is complete. Continue to Post-processing to apply it to the game.'
    onekey_translate_again: str = 'Translate Again'
    onekey_continue_post_processing: str = 'Continue to Post-processing →'
    onekey_input_folder_missing_does_not_exist: str = 'The input folder is missing or does not exist'
    onekey_output_folder_not_configured: str = 'The output folder is not configured'
    onekey_no_translation_provider_active: str = 'No translation provider is active'
    onekey_ready_translate_2: str = '✔ Ready to translate.'
    onekey_output_folder_does_not_exist: str = 'The output folder does not exist: {output_dir}'
    onekey_target_folder_does_not_exist: str = 'The target folder does not exist: {input_dir}'
    onekey_output_folder_does_not_contain_translation_files: str = 'The output folder does not contain translation files (.rpy)'
    onekey_translation_already_being_applied_please_wait: str = 'Translation is already being applied. Please wait...'
    onekey_translation_applied: str = 'Translation Applied'
    onekey_export_complete: str = 'Export Complete'
    onekey_created_missing_translation_patch_entries: str = 'Created a missing-translation patch at {patch_path} ({missing_count} entries)'
    onekey_failed_apply_translation: str = 'Failed to apply translation: {exc}'
    onekey_valid_ren_py_game_folder_detected: str = "✓ Valid Ren'Py game folder detected"
    onekey_no_game_subfolder_found_may_not_ren: str = "⚠ No game subfolder was found. This may not be a Ren'Py game."
    onekey_game_file_selected: str = '✓ Game file selected'
    onekey_path_does_not_exist: str = '✗ Path does not exist'
    onekey_finish_translation_first: str = 'Finish Translation First'
    onekey_incremental_content_has_not_been_applied_finish: str = (
        'The incremental content has not been applied. Finish translation, return to the toolbox,'
        ' and select Apply Translation.'
    )
    onekey_merge_completed: str = 'Merge Completed'
    onekey_merge_failed: str = 'Merge Failed'
    onekey_decompilation_completed_unren: str = 'Decompilation completed (UnRen)'
    onekey_decompilation_failed_game_may_incompatible_encrypted_use: str = 'Decompilation failed. The game may be incompatible, encrypted, or use unusual scripts: {e}'
    onekey_running_decompiler_automatically: str = (
        '\nRunning the decompiler automatically...'
    )
    onekey_decompilation_failed: str = '✗ Decompilation Failed'
    onekey_possible_causes_game_uses_encryption_obfuscation_ren: str = (
        "{decompile_msg}\n\nPossible causes:\n• The game uses encryption or obfuscation\n• The Ren'Py"
        " version is incompatible\n• The game's Python runtime is missing\n\nTry another decompiler "
        'or contact the developer.'
    )
    onekey_decompilation_failed_check_game_files: str = 'Decompilation failed. Check the game files.'
    onekey_rpa_archives_must_unpacked: str = '📦 RPA Archives Must Be Unpacked'
    onekey_use_rpa_unpacker_first_when_finishes_return: str = (
        '{status_msg}\n\nUse the RPA unpacker first. When it finishes, return here and select Extra'
        'ct Again.'
    )
    onekey_unpack_rpa_archives_first: str = 'Unpack the RPA archives first'
    onekey_unpacking_rpa_archives: str = '📦 Unpacking RPA archives...'
    onekey_running_rpa_unpacker_automatically: str = (
        '\nRunning the RPA unpacker automatically, please wait... (large games may take a few minutes)'
    )
    onekey_unpack_failed: str = '✗ Unpacking Failed'
    onekey_unpack_failed_hint: str = (
        '{unpack_msg}\n\nPossible causes:\n• The RPA archive is corrupted or incompatible\n• The game\'s bundled Python runtime is missing\n• No external unpacking tool is available\n\n'
        'Tip: click "Open RPA Unpacker" to unpack manually, or check the game files and try again.'
    )
    onekey_unpack_complete_no_scripts: str = (
        '{unpack_msg}\n\n⚠ No extractable scripts (.rpy/.rpyc) were found after unpacking. Check the output on the RPA Unpacker page.'
    )
    onekey_unpack_failed_check_game_files: str = 'Unpacking failed. Check the game files.'
    onekey_previous_incremental_cache_preserved_can_restored_manually: str = (
        '\nThe previous incremental cache was preserved at {name}/ and can be restored manually.'
    )
    onekey_project_assets_currently_unavailable: str = 'Project assets are currently unavailable: {exc}'
    onekey_character_world_workbench_page_not_found: str = 'The Character & World Workbench page was not found'
    onekey_could_not_open_workbench: str = 'Could not open the workbench: {exc}'
    onekey_could_not_open_translation_panel: str = 'Could not open the translation panel: {e}'
    onekey_tl_folder_not_found_missed_text_recovery: str = 'The TL folder was not found. Missed-text recovery was skipped: {tl_dir}'
    onekey_could_not_start_missed_text_recovery: str = 'Could not start missed-text recovery: {e}'
    onekey_missed_text_recovery_did_not_finish_main: str = 'Missed-text recovery did not finish. The main translation paths were restored.'
    onekey_missed_text_recovery_completed: str = 'Missed-text recovery completed'
    onekey_complete_following_setup_first: str = (
        '⚠ Complete the following setup first:\n'
    )
    onekey_could_not_open_missed_text_recovery: str = 'Could not open missed-text recovery: {e}'
    onekey_could_not_open_error_repair: str = 'Could not open Error Repair: {exc}'
    onekey_select_game_folder_first_2: str = 'Select a game folder first.'
    onekey_no_missing_translations_found_patch_not_needed: str = 'No missing translations were found. A patch is not needed.'
    onekey_could_not_export_language_patch: str = 'Could not export the language patch: {exc}'
    onekey_decompilation_failed_unren_error: str = 'Decompilation failed (UnRen error: {unren_error}): {e}'
    onekey_game_files_not_found: str = '✗ Game Files Not Found'
    onekey_output_folder_could_not_created: str = 'The output folder could not be created'
    onekey_input_output_folders_must_different: str = 'The input and output folders must be different'
    pack_unpack_invalid_part_size_enter_1g_1_5g: str = 'Invalid part size. Enter 1G, 1.5G, or 1024M'
    pack_unpack_part_size_must_greater_than_0: str = 'Part size must be greater than 0'
    pack_unpack_could_not_locate_game_folder_unren_fallback: str = 'Could not locate the game folder for UnRen fallback decompilation'
    pack_unpack_could_not_locate_game_folder_rpyc_cleanup: str = 'Could not locate the game folder for RPYC cleanup'
    pack_unpack_select_game_folder_containing_rpa_files: str = 'Select the game folder containing .rpa files'
    pack_unpack_direct_unpacking_unren_uses_game_s_python: str = "Direct unpacking (UnRen: uses the game's Python without launching it)"
    pack_unpack_try_game_s_python_first_then_fall: str = "Try the game's Python first, then fall back to external tools"
    pack_unpack_scripts_only_rpy_rpyc_skip_images_audio: str = 'Scripts only (.rpy/.rpyc; skip images, audio, and other assets)'
    pack_unpack_extract_script_files_only_faster_smaller_output: str = 'Extract script files only for faster, smaller output'
    pack_unpack_unpack: str = 'Unpack'
    pack_unpack_clean_temporary_files: str = 'Clean Temporary Files'
    pack_unpack_select_folder_package: str = 'Select a folder to package'
    pack_unpack_leave_blank_use_folder_name_rpa_parent: str = 'Leave blank to use folder-name.rpa in the parent folder'
    pack_unpack_splitting_enabled_images_rpa_produces_images_part001: str = 'With splitting enabled, images.rpa produces images.part001.rpa and similar files'
    pack_unpack_split_size: str = 'Split by Size'
    pack_unpack_create_independent_part001_rpa_part002_rpa_similar: str = 'Create independent .part001.rpa, .part002.rpa, and similar files'
    pack_unpack_e_g_1g_1024m: str = 'e.g. 1G or 1024M'
    pack_unpack_supports_1g_1_5g_1024m_1024mib_values: str = 'Supports 1G, 1.5G, 1024M, and 1024MiB; values without units use MiB'
    pack_unpack_pack: str = 'Pack'
    pack_unpack_select_game_folder_project_root_launcher_exe: str = 'Select the game folder, project root, or launcher .exe'
    pack_unpack_overwrite_existing_rpy_files_unrpyc_clobber: str = 'Overwrite existing .rpy files (unrpyc --clobber)'
    pack_unpack_direct_decompilation_unren_uses_game_s_python: str = "Direct decompilation (UnRen: uses the game's Python without launching it)"
    pack_unpack_try_unren_first_then_fall_back_unrpyc: str = 'Try UnRen first, then fall back to unrpyc'
    pack_unpack_decompile: str = 'Decompile'
    pack_unpack_try_unren_first_then_fall_back_unrpyc_2: str = 'Try UnRen first, then fall back to unrpyc v2'
    pack_unpack_clean_rpyc_files: str = 'Clean RPYC Files'
    pack_unpack_delete_rpyc_files_have_matching_decompiled_rpy: str = 'Delete RPYC files that have matching decompiled RPY files'
    pack_unpack_select_game_folder: str = 'Select Game Folder'
    pack_unpack_select_folder_package_2: str = 'Select Folder to Package'
    pack_unpack_select_rpa_output_base_file: str = 'Select RPA Output Base File'
    pack_unpack_rpa_files_rpa: str = 'RPA Files (*.rpa)'
    pack_unpack_select_game_folder_project_root: str = 'Select Game Folder or Project Root'
    pack_unpack_scanning_files: str = 'Scanning files...'
    pack_unpack_packing: str = 'Packing: {current}/{total} - {filename}'
    pack_unpack_packaging_complete_generated_rpa_file_s: str = 'Packaging complete. Generated {output_paths_count} RPA file(s)'
    pack_unpack_unpacking: str = 'Unpacking…'
    pack_unpack_trying_unren_fallback: str = 'Trying UnRen fallback…'
    pack_unpack_decompiling: str = 'Decompiling…'
    pack_unpack_cleaning_temporary_files: str = 'Cleaning temporary files…'
    pack_unpack_cleaning_rpyc_files: str = 'Cleaning RPYC files…'
    pack_unpack_removed_rpyc_file_s: str = 'Removed {removed} RPYC file(s)'
    pack_unpack_no_rpyc_files_found: str = 'No RPYC files found'
    pack_unpack_unpack_decompile_pack: str = '📦 Unpack / Decompile / Pack'
    pack_unpack_unpack_rpa_files: str = '📂 Unpack RPA Files'
    pack_unpack_game_folder: str = 'Game folder:'
    pack_unpack_pack_rpa_files: str = '📦 Pack as RPA Files'
    pack_unpack_source_folder: str = 'Source folder:'
    pack_unpack_output_base_file: str = 'Output base file:'
    pack_unpack_maximum_per_part: str = 'Maximum per part:'
    pack_unpack_decompile_rpyc_rpy: str = '🧩 Decompile RPYC → RPY'
    pack_unpack_game_folder_executable: str = 'Game folder / executable:'
    pack_unpack_preparing: str = 'Preparing…'
    pack_unpack_preparing_cleanup: str = 'Preparing cleanup…'
    pack_unpack_select_source_folder: str = 'Select a source folder'
    pack_unpack_source_folder_does_not_exist: str = 'The source folder does not exist'
    pack_unpack_packaging_task_already_running: str = 'A packaging task is already running'
    pack_unpack_cancelling_after_current_part_finishes_writing: str = 'Cancelling after the current part finishes writing...'
    pack_unpack_no_rpa_files_found_external_tools_unren: str = 'No RPA files were found, or the external tools/UnRen are unavailable'
    pack_unpack_decompiling_unren: str = 'Decompiling with UnRen…'
    pack_unpack_decompilation_complete_generated_rpy_files: str = 'Decompilation complete. Generated .rpy files'
    pack_unpack_unren_failed: str = ' (UnRen failed: {unren_error})'
    pack_unpack_skipped_file_s_without_matching_rpy_files: str = '; skipped {skipped} file(s) without matching .rpy files'
    pack_unpack_no_removable_rpyc_files_found_because_matching: str = 'No removable RPYC files found because matching .rpy files are missing'
    pack_unpack_no_removable_rpyc_files_found: str = 'No removable RPYC files found'
    pack_unpack_unpacking_task_already_running: str = 'An unpacking task is already running'
    pack_unpack_select_game_folder_2: str = 'Select a game folder'
    pack_unpack_unpacking_failed: str = 'Unpacking failed: {e}'
    pack_unpack_cleanup_task_already_running: str = 'A cleanup task is already running'
    pack_unpack_decompilation_task_already_running: str = 'A decompilation task is already running'
    pack_unpack_cleanup_failed: str = 'Cleanup failed: {e}'
    pack_unpack_select_game_folder_project_root_executable: str = 'Select a game folder, project root, or executable'
    pack_unpack_path_does_not_exist: str = 'The path does not exist'
    pack_unpack_decompilation_failed: str = 'Decompilation failed: {e}'
    pack_unpack_cleanup_failed_2: str = 'Cleanup failed: {exc}'
    pack_unpack_unavailable: str = 'Unavailable'
    pack_unpack_trying_direct_unpacking: str = 'Trying direct unpacking…'
    pack_unpack_unpacked_rpa_file_s: str = 'Unpacked {count} RPA file(s)'
    pack_unpack_unpacked_unren_fallback_check_game_folder_output: str = 'Unpacked with the UnRen fallback. Check the game folder for output'
    pack_unpack_unpacking_failed_2: str = 'Unpacking failed: {exc}'
    pack_unpack_error_generic: str = 'Unpacking failed. Check the logs for details.'

    @classmethod
    def pack_unpack_error(cls, code: str) -> str:
        """Return the unpack failure text for a stable code; unknown codes fall back."""
        return _PACK_UNPACK_ERROR_EN.get(str(code or ""), cls.pack_unpack_error_generic)
    pack_unpack_decompilation_failed_2: str = 'Decompilation failed: {exc}{extra}'
    pack_unpack_removed_temporary_item_s: str = 'Removed {removed} temporary item(s)'
    pack_unpack_no_temporary_files_need_cleaned: str = 'No temporary files need to be cleaned'
    pack_unpack_cancelled: str = 'Cancelled'
    pack_unpack_packaging_failed: str = 'Packaging failed: {message}'
    pack_unpack_direct_unpacking_failed_trying_external_tools: str = 'Direct unpacking failed; trying external tools…'
    pack_unpack_decompilation_completed_unren: str = 'Decompilation completed with UnRen'
    pack_unpack_directly_unpacked_archive_s: str = 'Directly unpacked {count} archive(s)'
    toolbox_search_tools: str = 'Search tools'
    toolbox_no_matching_tools: str = 'No matching tools'
    toolbox_try_another_keyword_clear_search_box: str = 'Try another keyword or clear the search box'
    toolbox_select_game_folder_first: str = 'Select a game folder first'
    toolbox_unknown_tool: str = 'Unknown tool: {key}'
    toolbox_tool_has_no_configured_page: str = 'Tool {key} has no configured page'
    toolbox_game_folder_not_selected: str = 'Game folder not selected'
    toolbox_select_game_folder_one_click_translation_first: str = 'Select a game folder in One-click Translation first'
    toolbox_failed_open: str = 'Failed to open'
    toolbox_could_not_open: str = 'Could not open "{title}": {exc}'
    toolbox_failed_open_translation_panel: str = 'Failed to open the translation panel: {exc}'
    default_language_select_project_root_containing_game: str = 'Select the project root containing game/'
    default_language_leave_blank_use_selected_language: str = 'Leave blank to use the selected language'
    default_language_sets_language_used_when_game_starts_steps: str = (
        'Sets the language used when the game starts.\n\nSteps:\n1. Select the project root\n2. Selec'
        't or enter a language name matching a folder under tl\n3. Click Set Default Language\n\nNot'
        'e: The language name must exactly match a folder under game/tl/.'
    )
    default_language_select_project_root: str = 'Select Project Root'
    default_language_set_default_language: str = '🌍 Set Default Language'
    default_language_default_language: str = '🗣️ Default Language'
    default_language_default_language_2: str = 'Default Language:'
    default_language_custom_name: str = 'Custom Name:'
    default_language_default_language_script_created: str = 'Default-language script created: {name}'
    default_language_select_project_folder: str = 'Select the project folder'
    default_language_select_enter_language_name: str = 'Select or enter a language name'
    default_language_language_folder_not_found_make_sure_translations: str = (
        'The language folder was not found: {tl_dir}\nMake sure translations for this language hav'
        'e been created.'
    )
    default_language_template_missing: str = 'Template is missing: {template}'
    default_language_failed_set_default_language: str = 'Failed to set the default language: {e}'
    text_preserve_do_not_translate: str = '🚫 Do Not Translate'
    text_preserve_manage_text_should_remain_unchanged_during_translation: str = 'Manage text that should remain unchanged during translation, such as proper nouns and code snippets.'
    text_preserve_save_settings: str = 'Save to Settings'
    text_preserve_load_settings: str = 'Load from Settings'
    text_preserve_deduplicate: str = 'Deduplicate'
    text_preserve_deduplicate_source_text_merge_notes_prefer_rows: str = 'Deduplicate by source text, merge notes, and prefer rows that already have notes.'
    text_preserve_delete_all_do_not_translate_entries_save: str = 'Delete all do-not-translate entries and save the change.'
    text_preserve_count_how_many_cached_output_entries_match: str = 'Count how many cached output entries match each do-not-translate rule.'
    text_preserve_rescan_variables: str = 'Rescan Variables'
    text_preserve_scan_game_folder_variable_references_replace_previous: str = 'Scan the game folder for [variable] references and replace the previous scan results.'
    text_preserve_do_not_translate_entries_cells_editable: str = 'Do-not-translate entries (cells are editable)'
    text_preserve_deleted_all_do_not_translate_entries_saved: str = 'Deleted all do-not-translate entries and saved the change.'
    text_preserve_loaded_do_not_translate_entries_settings: str = 'Loaded {converted_count} do-not-translate entries from settings.'
    text_preserve_saved_do_not_translate_entries_settings: str = 'Saved {entries_count} do-not-translate entries to settings.'
    text_preserve_select_excel_file: str = 'Select Excel File'
    text_preserve_save_excel_file: str = 'Save Excel File'
    text_preserve_analyzed_rules_across_cached_entries: str = 'Analyzed {counts_count} rules across {counted_item_total} cached entries.'
    text_preserve_found_variable_references_scanned: str = 'Found {new_preserves_count} variable references (scanned: {game_path}).'
    text_preserve_imported_do_not_translate_entries: str = 'Imported {items_count} do-not-translate entries.'
    text_preserve_there_no_do_not_translate_entries_analyze: str = 'There are no do-not-translate entries to analyze.'
    text_preserve_entries_changed_run_statistics_again: str = 'The entries changed. Run the statistics again.'
    text_preserve_no_folder_available_scan_set_input_output: str = 'No folder is available to scan. Set an input, output, or game folder first.'
    text_preserve_could_not_determine_which_folder_scan: str = 'Could not determine which folder to scan.'
    text_preserve_no_variable_references_found_list_cleared_scanned: str = 'No variable references were found. The list was cleared (scanned: {game_path}).'
    text_preserve_source_column_not_found_check_template: str = 'The Source column was not found. Check the template.'
    text_preserve_scan_failed: str = 'Scan failed: {e}'
    extract_tl_translation_extraction: str = 'Translation Extraction'
    extract_tl_extract_translatable_text_ren_py_game_tl: str = "Extract translatable text from a Ren'Py game into its tl folder"
    extract_tl_select_game_project_folder_contains_game_directory: str = 'Select the game project folder that contains the game directory'
    extract_tl_translation_folder_name_such_chinese_schinese: str = 'Translation folder name, such as chinese or schinese'
    extract_tl_start_extraction: str = 'Start Extraction'
    extract_tl_existing_translations_preserved_default_supplemental_extraction_works: str = (
        'Existing translations are preserved by default. Supplemental extraction works without an'
        ' exe and can be used if official extraction fails.'
    )
    extract_tl_advanced_options: str = '▶ Advanced Options'
    extract_tl_official_extraction: str = 'Official Extraction'
    extract_tl_use_game_engine_s_official_translation_extraction: str = "Use the game engine's official translation extraction (requires an exe)"
    extract_tl_supplemental_extraction: str = 'Supplemental Extraction'
    extract_tl_use_custom_ast_parsing_extract_text_missed: str = 'Use custom AST parsing to extract text missed by the official tool'
    extract_tl_only_required_official_extraction_leave_blank_find: str = 'Only required for official extraction; leave blank to find the .exe automatically'
    extract_tl_skip_hook_files: str = 'Skip Hook Files'
    extract_tl_filter_suspected_code_entries: str = 'Filter Suspected Code Entries'
    extract_tl_back_up_filtered_entries_filtered_suspicious_so: str = 'Back up filtered entries to _filtered_suspicious so they can be restored manually'
    extract_tl_merge_incremental_results_remove_duplicates_automatically: str = 'Merge Incremental Results and Remove Duplicates Automatically'
    extract_tl_merge_remove_duplicates: str = 'Merge & Remove Duplicates'
    extract_tl_open_filtered_backup: str = 'Open Filtered Backup'
    extract_tl_restore_selected_entries: str = 'Restore Selected Entries'
    extract_tl_suspected_code_lines_moved_tl_lang_filtered: str = (
        'Suspected code lines are moved to tl/<lang>/_filtered_suspicious/<timestamp>/restore_man'
        'ifest.csv after extraction. Set the restore column to 1, then restore them here.'
    )
    extract_tl_select_game_executable: str = 'Select Game Executable'
    extract_tl_executable_files_exe_py: str = 'Executable Files (*.exe *.py)'
    extract_tl_game_folder: str = 'Game Folder:'
    extract_tl_language_name: str = 'Language Name:'
    extract_tl_extraction_method: str = 'Extraction Method:'
    extract_tl_game_exe_optional: str = 'Game exe (Optional):'
    extract_tl_advanced_options_2: str = '▼ Advanced Options'
    extract_tl_extracting_translatable_text: str = 'Extracting translatable text...'
    extract_tl_merging_incremental_translations: str = 'Merging incremental translations...'
    extract_tl_no_filtered_backup_available_yet: str = 'No filtered backup is available yet'
    extract_tl_restoring_filtered_entries: str = 'Restoring filtered entries...'
    extract_tl_folder_does_not_exist: str = 'Folder does not exist: {game_dir}'
    extract_tl_game_directory_not_found: str = 'The game directory was not found'
    extract_tl_tl_subfolder_not_found: str = 'The tl subfolder was not found: {tl_dir}'
    extract_tl_no_exe_found_official_extraction_disabled_supplemental: str = 'No exe was found. Official extraction was disabled and supplemental extraction will be used.'
    extract_tl_incremental_mode: str = 'Incremental Mode'
    extract_tl_existing_tl_files_found_incremental_extraction_preserve: str = 'Existing tl files were found. Incremental extraction will preserve translated content.'
    extract_tl_extraction_complete: str = 'Extraction Complete'
    extract_tl_extraction_failed: str = 'Extraction Failed'
    extract_tl_merge_complete: str = 'Merge Complete'
    extract_tl_restore_complete: str = 'Restore Complete'
    extract_tl_nothing_restored: str = 'Nothing Restored'
    extract_tl_leave_blank_find_exe_automatically: str = 'Leave blank to find the .exe automatically'
    extract_tl_automatic_merge_complete: str = 'Automatic Merge Complete'
    extract_tl_automatic_merge_failed: str = 'Automatic Merge Failed'
    extract_tl_failed_read_default_encoding: str = (
        'Failed to read with the default encoding {renpy_default_encoding}:\n{e}'
    )
    workbench_not_configured: str = 'Not configured'
    workbench_not_set: str = 'Not set'
    workbench_latest_analysis_source: str = 'Latest analysis source: {source_summary}'
    workbench_character_sync_source: str = 'Character sync source: {payload_get_source_summary}'
    workbench_character_sync_complete_new_drafts_ready_review: str = 'Character sync is complete. {added} new drafts are ready for review.'
    workbench_manage_worldbuilding_character_profiles_prompt_context_current: str = (
        'Manage worldbuilding, character profiles, and prompt context for the current output proj'
        'ect, and generate AI drafts on demand.'
    )
    workbench_current_project_summary: str = 'Current Project Asset Summary'
    workbench_single_view_current_api_paths_workbench_state: str = 'Review the current API, model, language pair, and workbench asset state in one place.'
    workbench_analysis_shortcuts: str = 'AI Extraction and Analysis Actions'
    workbench_generate_ai_drafts_demand_current_scope_then: str = 'Generate character drafts for the current scope or the full project, with linked shortcuts.'
    workbench_generate_current_scope_drafts: str = 'Generate Current-Scope Drafts'
    workbench_reanalyze_full_project: str = 'Reanalyze Full Project'
    workbench_sync_character_names: str = 'Sync Character Names'
    workbench_apply_all_drafts: str = 'Apply All Drafts'
    workbench_apply_all_and_enable: str = 'Apply All & Enable'
    workbench_import_as_drafts: str = 'Import for Review'
    workbench_import_apply_enable: str = 'Import & Enable'
    workbench_export_project_assets: str = 'Export Project Assets'
    workbench_clear_current_characters: str = 'Clear Current Characters'
    workbench_open_local_glossary: str = 'Open Local Glossary'
    workbench_open_do_not_translate_list: str = 'Open Do-Not-Translate List'
    workbench_open_custom_prompts: str = 'Open Custom Prompts'
    workbench_ready: str = 'Ready'
    workbench_worldbuilding: str = 'Worldbuilding'
    workbench_edit_approved_worldbuilding_left_review_ai_drafts: str = 'Edit approved worldbuilding on the left and review AI drafts and raw responses on the right.'
    workbench_inject_worldbuilding_context: str = 'Inject Worldbuilding Context'
    workbench_approved_worldbuilding: str = 'Approved Worldbuilding'
    workbench_content_inserted_directly_generated_prompts: str = 'This content is inserted directly into generated prompts.'
    workbench_ai_draft_preview: str = 'AI Draft Preview'
    workbench_generated_content_remains_draft_until_you_apply: str = 'Generated content remains a draft until you apply it.'
    workbench_generate_current_scope: str = 'Generate Current Scope'
    workbench_expand_reanalyze: str = 'Expand & Reanalyze'
    workbench_apply_worldbuilding_draft: str = 'Apply Worldbuilding Draft'
    workbench_generated_worldbuilding_drafts_appear_here: str = 'Generated worldbuilding drafts appear here.'
    workbench_if_parsing_fails_raw_model_response_appears: str = 'If parsing fails, the raw model response appears here.'
    workbench_character_card_workbench: str = 'Character Card Workbench'
    workbench_browse_characters_left_edit_approved_cards_center: str = 'Browse characters on the left, edit approved cards in the center, and review AI drafts on the right.'
    workbench_inject_character_card_context: str = 'Inject Character Card Context'
    workbench_generate_all_character_cards: str = 'Generate All Character Cards'
    workbench_regenerate_current_character: str = 'Regenerate Current Character'
    workbench_apply_current_character_draft: str = 'Apply Current Character Draft'
    workbench_apply_current_and_enable: str = 'Apply Current & Enable'
    workbench_add_blank_character_card: str = 'Add Blank Character Card'
    workbench_delete_current_character: str = 'Delete Current Character'
    workbench_character_list: str = 'Character List'
    workbench_synced_character_candidates_added_here_review: str = 'Synced character candidates are added here for review.'
    workbench_search_characters: str = 'Search names, aliases, or keywords'
    workbench_filter_all: str = 'All'
    workbench_filter_pending: str = 'Pending'
    workbench_filter_applied: str = 'Applied'
    workbench_character_count: str = 'Showing {visible} of {total}'
    workbench_approved_character_card: str = 'Approved Character Card'
    workbench_manual_edits_saved_immediately_current_project_assets: str = 'Manual edits are saved immediately to the current project assets.'
    workbench_enable_character_card: str = 'Enable This Character Card'
    workbench_mark_main_character: str = 'Mark as Main Character'
    workbench_character_draft_preview: str = 'Character Draft Preview'
    workbench_ai_generated_character_drafts_appear_here: str = 'AI-generated character drafts appear here.'
    workbench_select_character_view_draft_details: str = 'Select a character to view draft details.'
    workbench_if_parsing_fails_raw_model_response_appears_2: str = 'If parsing fails, the raw model response appears here.'
    workbench_prompt_match_preview: str = 'Prompt Match Preview'
    workbench_enter_sample_source_text_preview_matching_character: str = 'Enter sample source text to preview matching character cards and the final injected context.'
    workbench_enter_one_more_lines_sample_source_text: str = 'Enter one or more lines of sample source text.'
    workbench_no_sample_source_text_entered: str = 'No sample source text entered.'
    workbench_injected_context: str = 'Injected Context'
    workbench_preview_how_workbench_context_inserted_final_prompt: str = 'Preview how workbench context is inserted into the final prompt.'
    workbench_worldbuilding_context_appears_here: str = 'Worldbuilding context appears here.'
    workbench_matched_character_context_appears_here: str = 'Matched character context appears here.'
    workbench_final_injected_context_appears_here: str = 'The final injected context appears here.'
    workbench_enabled: str = 'Enabled'
    workbench_not_enabled: str = 'Not enabled'
    workbench_total_enabled: str = '{cards_count} total, {enabled_cards} enabled'
    workbench_unnamed_character: str = 'Unnamed character'
    workbench_none: str = 'None'
    workbench_character: str = 'Character {len_cards}'
    workbench_running_ai_analysis: str = 'Running AI analysis...'
    workbench_ai_drafts_ready_review_them_right_before: str = 'AI drafts are ready. Review them on the right before applying.'
    workbench_ai_draft_generation_complete: str = 'AI draft generation is complete.'
    workbench_syncing_character_candidates: str = 'Syncing character candidates...'
    workbench_worldbuilding_draft_has_been_applied: str = 'The worldbuilding draft has been applied.'
    workbench_character_draft_has_been_applied: str = 'The character draft has been applied.'
    workbench_all_drafts_have_been_applied: str = 'All drafts have been applied.'
    workbench_character_worldbuilding_workbench: str = 'Character & Worldbuilding Workbench'
    workbench_overview: str = 'Overview'
    workbench_worldbuilding_2: str = 'Worldbuilding'
    workbench_character_cards: str = 'Character Cards'
    workbench_prompt_preview: str = 'Prompt Preview'
    workbench_current_api: str = 'Current API'
    workbench_current_model: str = 'Current Model'
    workbench_language_pair: str = 'Language Pair'
    workbench_input_folder: str = 'Input Folder'
    workbench_output_folder: str = 'Output Folder'
    workbench_project_folder: str = 'Project Folder'
    workbench_tl_folder: str = 'TL Folder'
    workbench_draft_status: str = 'Draft Status'
    workbench_cache_status: str = 'Cache Status'
    workbench_cache_sqlite: str = 'SQLite cache · {item_count} entries'
    workbench_cache_json: str = 'JSON cache · {item_count} entries'
    workbench_cache_unreadable: str = 'Cache read failed'
    workbench_project_name: str = 'Project Name'
    workbench_genre: str = 'Genre'
    workbench_setting_summary: str = 'Setting Summary'
    workbench_era_environment: str = 'Era & Environment'
    workbench_tone_style: str = 'Tone & Style'
    workbench_narrative_rules: str = 'Narrative Rules'
    workbench_formatting_rules: str = 'Formatting Rules'
    workbench_spoiler_notes: str = 'Spoiler Notes'
    workbench_reference_notes: str = 'Additional Reference Notes'
    workbench_structured_draft: str = 'Structured Draft'
    workbench_raw_response_error_preview: str = 'Raw Response / Error Preview'
    workbench_character_name: str = 'Character Name'
    workbench_suggested_translation: str = 'Suggested Translation'
    workbench_aliases: str = 'Aliases'
    workbench_match_keywords: str = 'Match Keywords'
    workbench_identity: str = 'Identity'
    workbench_personality: str = 'Personality'
    workbench_speech_style: str = 'Speech Style'
    workbench_relationship_notes: str = 'Relationship Notes'
    workbench_translation_notes: str = 'Translation Notes'
    workbench_sample_lines: str = 'Sample Lines'
    workbench_worldbuilding_context: str = 'Worldbuilding Context'
    workbench_character_context: str = 'Character Context'
    workbench_final_injected_context: str = 'Final Injected Context'
    workbench_no_ai_analysis_has_been_run_yet: str = 'No AI analysis has been run yet.'
    workbench_project_name_2: str = 'Project name: {draft_get_project_name}'
    workbench_genre_2: str = 'Genre: {draft_get_genre}'
    workbench_setting_summary_2: str = 'Setting summary: {draft_get_setting_summary}'
    workbench_era_environment_2: str = 'Era and environment: {draft_get_era_background}'
    workbench_tone_style_2: str = 'Tone and style: {draft_get_tone_style}'
    workbench_narrative_rules_2: str = 'Narrative rules: {draft_get_narrative_rules}'
    workbench_formatting_rules_2: str = 'Formatting rules: {draft_get_format_rules}'
    workbench_spoiler_notes_2: str = 'Spoiler notes: {draft_get_spoiler_notes}'
    workbench_reference_notes_preview: str = 'Additional reference notes: {reference_notes}'
    workbench_character_name_2: str = 'Character name: {draft_get_name}'
    workbench_suggested_translation_2: str = 'Suggested translation: {draft_get_name_translation}'
    workbench_identity_2: str = 'Identity: {identity_or_empty_value}'
    workbench_personality_2: str = 'Personality: {personality_or_empty_value}'
    workbench_speech_style_2: str = 'Speech style: {speech_style_or_empty_value}'
    workbench_relationship_notes_2: str = 'Relationship notes: {relationship_notes_or_empty_value}'
    workbench_translation_notes_2: str = 'Translation notes: {prompt_notes_or_empty_value}'
    workbench_translation_task_running_ai_generation_character_sync: str = 'A translation task is running. AI generation and character sync are temporarily disabled.'
    workbench_ai_analysis_failed: str = 'AI analysis failed'
    workbench_there_no_worldbuilding_draft_apply: str = 'There is no worldbuilding draft to apply.'
    workbench_select_character_first: str = 'Select a character first.'
    workbench_selected_character_has_no_draft_apply: str = 'The selected character has no draft to apply.'
    workbench_there_no_drafts_apply: str = 'There are no drafts to apply.'
    workbench_ren_py_toolbox_page_unavailable: str = "The Ren'Py Toolbox page is unavailable."
    workbench_main: str = 'Main'
    workbench_off: str = 'Off'
    workbench_draft: str = 'Draft'
    workbench_sample_lines_2: str = 'Sample lines:'
    workbench_current_api_does_not_support_ai_analysis: str = (
        'The current API does not support AI analysis. Switch to an OpenAI, Google, Anthropic, or'
        ' SakuraLLM-compatible API.'
    )
    workbench_ai_analysis_running_please_wait: str = 'AI analysis is running. Please wait.'
    workbench_character_sync_running_please_wait: str = 'Character sync is running. Please wait.'
    workbench_ai_analysis_failed_2: str = 'AI analysis failed.'
    workbench_unknown_analysis_mode: str = 'Unknown analysis mode.'
    workbench_select_import_file: str = 'Import Workbench Project Assets'
    workbench_select_export_file: str = 'Export Workbench Project Assets'
    workbench_json_file_filter: str = 'JSON Files (*.json)'
    workbench_import_failed: str = 'Import failed: {error}'
    workbench_imported_as_drafts: str = 'Imported {count} character cards for review.'
    workbench_import_applied: str = 'Imported {count} character cards and enabled prompt injection.'
    workbench_export_failed: str = 'Export failed: {error}'
    workbench_export_complete: str = 'Project assets exported to: {path}'
    workbench_no_characters_to_clear: str = 'The current project has no character data to clear.'
    workbench_clear_current_characters_confirm: str = 'Delete {cards} applied character cards and {drafts} pending drafts from the current project? Worldbuilding, terminology, and other projects are not affected. Export a backup first if needed.'
    workbench_current_characters_cleared: str = 'Character data for the current project has been cleared.'

    # 通用界面补充
    error: str = "Error"
    success: str = "Success"
    complete: str = "Complete"
    notice: str = "Notice"
    browse: str = "Browse"
    ready: str = "Ready"
    enabled: str = "Enabled"
    disabled: str = "Disabled"
    available: str = "Available"
    current_scope: str = "Current scope"
    full_project: str = "Full project"
    list_separator: str = ", "
    rule_statistics_no_cached_entries: str = "No cached entries were found. Run a translation first or check the current output cache."
    rule_statistics_unavailable: str = "Unable to calculate hit statistics."

    # 未自动迁移的动态工具文案
    android_build_environment_check_completed: str = "Environment check completed."
    android_build_environment_check_failed: str = "Environment check failed."
    android_build_sdk_installation_completed: str = "SDK installation completed."
    android_build_sdk_installation_failed: str = "SDK installation failed."
    android_build_signing_key_generated: str = "Signing key generated."
    android_build_signing_key_generation_failed: str = "Signing key generation failed."
    font_replace_font_pack_injected_into_tl: str = "The font pack was injected into tl/{target_lang}."
    font_replace_modified_files_with_replacements: str = (
        "Modified {replaced_files} file(s) with {replaced_count} replacement(s).{backup_info}"
    )
    local_glossary_translation_failed_check_engine_logs: str = "Glossary translation failed. Check the configured engine and logs."
    local_glossary_scanning_term_candidates_percent: str = "Scanning term candidates... {percent}%"
    local_glossary_candidate_scan_failed_check_folder_logs: str = "The term candidate scan failed. Check the selected folder and logs."
    local_glossary_no_usable_term_candidates_generated: str = "No usable term candidates were generated."
    local_glossary_scan_steps_reported_warnings: str = "\nSome scan steps reported warnings."
    onekey_extracting_text: str = "Extracting text..."
    onekey_text_extraction_completed: str = "Text extraction completed"
    onekey_text_extraction_failed: str = "Text extraction failed"
    onekey_text_extraction_failed_with_error: str = "Text extraction failed: {error}"
    onekey_applying_translation: str = "Applying translation..."
    onekey_incremental_translation_merge_failed: str = "Failed to merge the incremental translation files"
    onekey_incremental_translation_applied: str = "The incremental translation was applied successfully"
    onekey_incremental_files_merged: str = "The incremental files were merged and duplicates removed"
    onekey_incremental_files_merge_failed: str = "Could not merge the incremental files"
    onekey_project_assets_summary: str = (
        "Current project assets: worldbook {worldbook_status}, {character_count} character cards, "
        "{glossary_count} glossary terms, {preserve_count} protected terms, {candidate_count} term candidates, "
        "and {draft_count} character drafts."
    )
    extract_tl_incremental_results_merged: str = "Incremental results were merged successfully."
    extract_tl_incremental_results_merge_failed: str = "Failed to merge the incremental results."
    extract_tl_translation_extraction_completed: str = "Translation extraction completed successfully."
    extract_tl_translation_extraction_failed: str = "Translation extraction failed."
    extract_tl_entries_restored: str = "The selected entries were restored successfully."
    extract_tl_no_entries_restored: str = "No entries were restored."
    workbench_draft_summary: str = (
        "Worldbuilding draft: {worldbook_status}; character drafts: {draft_count}; latest scope: {scope}"
    )
    workbench_aliases_preview: str = "Aliases: {aliases}"
    workbench_match_keywords_preview: str = "Match keywords: {keywords}"
    workbench_matched_characters: str = "Matched characters: {names}"

    # 工具箱入口注册表
    toolbox_group_flow: str = "Recommended Workflow"
    toolbox_group_translate: str = "Translation Methods"
    toolbox_group_asset: str = "Resources & Glossaries"
    toolbox_group_engineer: str = "Engineering & Repair"
    toolbox_page_header_description: str = "Manage translation workflows, text processing, terminology assets, and engineering tools"
    toolbox_group_count: str = "{COUNT} tools"
    toolbox_tool_continue_translation_title: str = 'Continue Translation'
    toolbox_tool_continue_translation_description: str = 'Resume the unfinished translation task'
    toolbox_tool_one_key_translate_title: str = 'One-click Translation'
    toolbox_tool_one_key_translate_description: str = 'Select a game folder, then extract and translate text automatically'
    toolbox_tool_proofreading_title: str = 'Review & Polish'
    toolbox_tool_proofreading_description: str = 'Review quality reports, proofread or polish translations, then export them'
    toolbox_tool_apply_translation_title: str = 'Apply Translation'
    toolbox_tool_apply_translation_description: str = "Write translation results to the game's TL directory"
    toolbox_tool_font_replace_title: str = 'Font Injection'
    toolbox_tool_font_replace_description: str = 'Inject a bundled font pack and its UI adaptation scripts'
    toolbox_tool_add_language_title: str = 'Add Language Menu'
    toolbox_tool_add_language_description: str = 'Add a language-switching menu to the game'
    toolbox_tool_set_default_language_title: str = 'Set Default Language'
    toolbox_tool_set_default_language_description: str = 'Set the language used when the game starts'
    toolbox_tool_extract_to_tl_title: str = 'Extract to TL'
    toolbox_tool_extract_to_tl_description: str = 'Use official or runtime extraction methods'
    toolbox_tool_direct_rpy_translate_title: str = 'Translate RPY Files'
    toolbox_tool_direct_rpy_translate_description: str = 'Translate tl/*.rpy files directly'
    toolbox_tool_hook_translate_title: str = 'HOOK Translation'
    toolbox_tool_hook_translate_description: str = 'Run the game, capture its text, and translate it'
    toolbox_tool_source_translate_title: str = 'Source Translation'
    toolbox_tool_source_translate_description: str = 'Translate game/*.rpy source files directly'
    toolbox_tool_hook_supplement_title: str = 'Complete Missing Translations'
    toolbox_tool_hook_supplement_description: str = 'Find missed text and generate a supplemental script'
    toolbox_tool_extract_json_title: str = 'Extract Text to JSON'
    toolbox_tool_extract_json_description: str = 'Export JSON for manual translation, then import it into TL'
    toolbox_tool_local_glossary_title: str = 'Local Glossary'
    toolbox_tool_local_glossary_description: str = 'Manage terminology to keep proper names consistent'
    toolbox_tool_text_preserve_title: str = 'Do Not Translate List'
    toolbox_tool_text_preserve_description: str = 'Manage variables and code that should not be translated'
    toolbox_tool_honorific_placeholder_title: str = 'Honorific Bridge'
    toolbox_tool_honorific_placeholder_description: str = 'Handle text that combines honorifics and variables'
    toolbox_tool_ma_suite_title: str = 'Structured Export'
    toolbox_tool_ma_suite_description: str = 'Export Excel workbooks and structured translation scripts'
    toolbox_tool_batch_correction_title: str = 'Batch Corrections'
    toolbox_tool_batch_correction_description: str = 'Correct quality-report translations in bulk with Excel'
    toolbox_tool_name_extraction_title: str = 'Name Extraction'
    toolbox_tool_name_extraction_description: str = 'Scan scripts and JSON files to create a character-name list'
    toolbox_tool_pack_unpack_title: str = 'Pack / Unpack'
    toolbox_tool_pack_unpack_description: str = 'Unpack RPA archives or package game assets'
    toolbox_tool_error_repair_title: str = 'Error Repair'
    toolbox_tool_error_repair_description: str = 'Scan for and fix common script errors'
    toolbox_tool_translation_reuse_title: str = 'Reuse Updated Translations'
    toolbox_tool_translation_reuse_description: str = 'Fill empty entries in a new version with matching previous translations'
    toolbox_tool_formatter_title: str = 'Code Formatter'
    toolbox_tool_formatter_description: str = 'Format .rpy files'
    toolbox_tool_android_build_title: str = 'Android Build'
    toolbox_tool_android_build_description: str = 'Install the SDK, generate signing keys, and build an APK'
    toolbox_tool_html_import_title: str = 'HTML Import'
    toolbox_tool_html_import_description: str = 'Convert translation text among HTML, TXT, and Excel'
    toolbox_tool_game_mod_title: str = 'Game Mod Injection'
    toolbox_tool_game_mod_description: str = 'Inject common mods such as gallery unlockers and utilities'

    # 终极结构导出
    ma_suite_title: str = "Structured Translation Suite"
    ma_suite_description: str = "Extract game source into Excel and generate structured translation files (translate_names/others.rpy + replace.rpy)."
    ma_suite_game_path: str = "Game Path:"
    ma_suite_game_path_placeholder: str = "Select the project folder containing game, or select an exe"
    ma_suite_select_folder: str = "Select Folder"
    ma_suite_select_exe: str = "Select exe"
    ma_suite_language_name: str = "Language Name:"
    ma_suite_language_name_tooltip: str = "tl/<language> folder name, such as chinese, schinese, or tchinese"
    ma_suite_run_official_extraction_first: str = "Run Official Extraction First (Off by Default)"
    ma_suite_extraction_mode: str = "Extraction Mode:"
    ma_suite_mode_standard: str = "Standard Only (Stable)"
    ma_suite_mode_external: str = "Standard + External Files (.json/.yml)"
    ma_suite_mode_aggressive: str = "Standard + External + Aggressive Scan (Use Carefully)"
    ma_suite_mode_tooltip: str = "Suite modes: 1=standard, 2=external files, 3=external files + aggressive scan"
    ma_suite_generate_emoji_mapping: str = "Generate Emoji Replacement Map"
    ma_suite_generate_emoji_mapping_tooltip: str = "Scan effect tags ({} / []) under tl/<lang> and generate pre/post-translation replacement maps"
    ma_suite_official_exe_optional: str = "Official Extraction exe (Optional):"
    ma_suite_official_exe_placeholder: str = "Only needed for official extraction; leave blank to detect automatically"
    ma_suite_generate_structure: str = "Generate Structured Files"
    ma_suite_emoji_helper: str = "Emoji Replacement Helper (Batch Folder)"
    ma_suite_emoji_helper_description: str = "Use the mapping table to apply pre- or post-translation replacements to all .rpy files in a folder."
    ma_suite_target_folder: str = "Target Folder:"
    ma_suite_target_folder_placeholder: str = "Select a folder to process, such as game/tl/Chinese"
    ma_suite_prepare_folder: str = "Protect Tags Before Translation (Folder)"
    ma_suite_restore_folder: str = "Restore After Translation (Folder)"
    ma_suite_select_rpy_folder: str = "Select a Folder Containing .rpy Files"
    ma_suite_select_game_folder: str = "Select Game Folder"
    ma_suite_select_game_executable: str = "Select Game Executable"
    ma_suite_select_official_exe: str = "Select exe for Official Extraction"
    ma_suite_executable_filter: str = "Executable Files (*.exe *.py);;All Files (*)"
    ma_suite_select_game_path_first: str = "Select a game folder or exe first"
    ma_suite_generating_structure: str = "Generating structured files..."
    ma_suite_no_result_check_paths: str = "No result was generated. Check the path and tl folder."
    ma_suite_no_result: str = "No Result Generated"
    ma_suite_emoji_mapping_summary: str = "\nEmoji/Tag mappings: {emoji_count} -> {emoji_dir}"
    ma_suite_result_summary: str = "{names_count} character names, {others_count} other entries, {replace_count} replacements"
    ma_suite_deleted_summary: str = "; {deleted_count} deleted"
    ma_suite_output_summary: str = "{summary}\nOutput folder: {output}{extra}"
    ma_suite_complete_status: str = "Complete: {output}"
    ma_suite_output_written: str = "Written to the output folder"
    ma_suite_execution_failed: str = "Execution Failed"
    ma_suite_select_target_folder: str = "Select a folder to process"
    ma_suite_folder_does_not_exist: str = "Folder does not exist: {target}"
    ma_suite_folder_processed: str = "Processed folder: {target}\nSucceeded: {success} files; failed: {failed} files\nBackup: {backup_path}"
    ma_suite_select_game_path_above: str = "Select a game folder or exe above first"
    ma_suite_game_folder_not_found: str = "The game folder was not found: {game_folder}"
