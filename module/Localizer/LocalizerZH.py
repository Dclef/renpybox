
_PACK_UNPACK_ERROR_ZH = {
    "UNSAFE_PATH": "RPA 归档包含不安全路径，已拒绝解包。",
    "UNSAFE_INDEX": "无法安全读取 RPA 索引，已拒绝解包。",
    "VALIDATION_FAILED": "RPA 路径安全校验失败。",
    "NO_GAME_PYTHON": "未找到游戏自带的 Python 运行时，无法直接解包。",
    "MISSING_RESOURCE": "缺少解包所需的资源文件。",
    "INVALID_DIR": "游戏目录不存在或路径无效。",
    "EXTRACTOR_FAILED": "游戏自带的 Ren'Py 解包器执行失败。",
    "UNAVAILABLE": "未找到可解包的 RPA 文件，或所有解包方式均失败。",
    "UNREN_SKIPPED": "前两种解包方式失败，UnRen 兜底因安全校验不可用而跳过。",
}


class LocalizerZH():

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
    add: str = "新增"
    edit: str = "修改"
    none: str = "无"
    back: str = "返回"
    next: str = "下一个"
    stop: str = "停止"
    start: str = "开始"
    timer: str = "定时器"
    close: str = "关闭"
    alert: str = "提醒"
    warning: str = "警告"
    confirm: str = "确认"
    cancel: str = "取消"
    later: str = "稍后"
    auto: str = "自动"
    wiki: str = "功能说明"
    open: str = "打开"
    select: str = "选择"
    inject: str = "注入"
    filter: str = "过滤"
    search: str = "搜索"
    generate: str = "生成"
    placeholder: str = "请输入关键词 …"
    task_success: str = "任务执行成功 …"
    alert_no_data: str = "没有有效数据 …"
    alert_reset_timer: str = "将重置定时器，是否确认 … ？"
    alert_reset_translation: str = "将重置尚未完成的翻译任务，是否确认开始新的翻译任务 … ？"
    search_prev: str = "上一个"
    search_next: str = "下一个"
    search_prev_match: str = "上一个匹配项"
    search_next_match: str = "下一个匹配项"
    search_regex_on: str = "正则模式\n当前状态：已启用"
    search_regex_off: str = "正则模式\n当前状态：未启用"
    search_regex_invalid: str = "正则表达式无效"
    search_no_match: str = "未找到匹配项"
    search_regex_btn: str = "正则"
    search_match_info: str = "第 {current} 项，共 {total} 项"
    search_no_result: str = "无结果"
    current_status: str = "当前状态："

    # 主页面
    app_close_message_box: str = "确定是否退出程序 … ？"
    app_new_version: str = " 有新版本"
    app_new_version_toast: str = "发现新版本 {VERSION}"
    app_new_version_update: str = " 下载中 {PERCENT}"
    app_new_version_failure: str = "下载更新失败："
    app_new_version_success: str = "更新已下载"
    app_new_version_downloaded: str = " 待安装"
    app_new_version_waiting_restart: str = "正在重启并安装"
    app_new_version_apply_failure: str = "应用更新失败："
    app_theme_btn: str = "切换主题"
    app_language_btn: str = "语言"
    app_settings_page: str = "应用设置"
    app_platform_page: str = "接口管理"
    app_project_page: str = "项目设置"
    app_renpy_toolbox_page: str = "Ren'Py 工具箱"
    app_workbench_page: str = "角色 / 世界观工作台"
    app_translation_page: str = "翻译任务"
    app_agent_page: str = "Agent 助手"
    app_proofreading_page: str = "校对任务"
    app_basic_settings_page: str = "基础设置"
    app_expert_settings_page: str = "专家设置"
    app_glossary_page: str = "术语表"
    app_text_preserve_page: str = "文本保护"
    app_text_replacement_page: str = "文本替换"
    app_pre_translation_replacement_page: str = "译前替换"
    app_post_translation_replacement_page: str = "译后替换"
    app_custom_prompt_navigation_item: str = "翻译提示"
    app_custom_prompt_zh_page: str = "中文提示词"
    app_custom_prompt_en_page: str = "英文提示词"
    app_laboratory_page: str = "实验室"
    app_treasure_chest_page: str = "百宝箱"

    # 路径
    path_bilingual: str = "双语对照"
    path_glossary_export: str = "导出_术语表"
    path_text_preserve_export: str = "导出_文本保护"
    path_pre_translation_replacement_export: str = "导出_译前替换"
    path_post_translation_replacement_export: str = "导出_译后替换"
    path_result_check_kana: str = "结果检查_假名残留.json"
    path_result_check_hangeul: str = "结果检查_谚文残留.json"
    path_result_check_text_preserve: str = "结果检查_文本保护.json"
    path_result_check_similarity: str = "结果检查_相似度较高.json"
    path_result_check_glossary: str = "结果检查_术语表未生效.json"
    path_result_check_mixed_translation: str = "结果检查_混合翻译错误.json"
    path_result_check_untranslated: str = "结果检查_未翻译的条目.json"
    path_result_check_retry_count_threshold: str = "结果检查_重试次数达到阈值.json"
    path_result_batch_correction: str = "批量修正.xlsx"
    path_result_name_field_extraction: str = "姓名字段提取.xlsx"

    # 日志
    log_proxy: str = "网络代理已启用 …"
    log_expert_mode: str = "专家模式已启用 …"
    log_api_test_fail: str = "接口测试失败 … "
    log_task_fail: str = "翻译任务失败 …"
    log_read_file_fail: str = "文件读取失败 …"
    log_write_file_fail: str = "文件写入失败 …"
    log_read_cache_file_fail: str = "从文件读取缓存数据失败 …"
    log_write_cache_file_fail: str = "向文件写入缓存数据失败 …"
    log_no_cache_data: str = "没有找到缓存数据，请先进行翻译 …"
    log_crash: str = "出现严重错误，程序即将退出，错误信息已保存至日志文件 …"
    cli_verify_folder: str = "参数发生错误：无效的路径 …"
    cli_verify_language: str = "参数发生错误：无效的语言 …"
    translator_max_round: str = "最大重试轮次"
    translator_current_round: str = "当前重试轮次"
    translator_api_url: str = "接口地址"
    translator_name: str = "接口名称"
    translator_model: str = "模型名称"
    translator_writing: str = "正在写入翻译数据，等稍候 …"
    translator_done: str = "所有文本均已翻译，翻译任务已结束 …"
    translator_fail: str = "已到最大翻译轮次，仍有部分文本未翻译，请检查翻译结果 …"
    translator_stop: str = "翻译任务已停止 …"
    translator_write: str = "翻译结果已保存至 {PATH} 目录 …"
    translator_task_generation_log: str = "任务生成已完成，共生成 {COUNT} 个任务 …"
    translator_rule_filter_log: str = "规则过滤已完成，共过滤 {COUNT} 个无需翻译的条目 …"
    translator_language_filter_log: str = "语言过滤已完成，共过滤 {COUNT} 个不包含目标语言的条目 …"
    translator_mtool_optimizer_pre_log: str = "MToolOptimizer 预处理已完成，共过滤 {COUNT} 个包含重复子句的条目 …"
    translator_mtool_optimizer_post_log: str = "MToolOptimizer 后处理已完成 …"
    translator_task_response_think: str = "模型思考内容：\n"
    translator_task_response_result: str = "模型回复内容：\n"
    translator_response_check_fail: str = "译文文本未通过检查，将在下一轮次的翻译中自动重试"
    translator_response_check_fail_all: str = "全部译文文本未通过检查，将在下一轮次的翻译中自动重试"
    translator_response_check_fail_part: str = "部分译文文本未通过检查，将在下一轮次的翻译中自动重试"
    translator_response_check_fail_line_stats: str = "失败行数 {FAILED}/{TOTAL}"
    translator_single_line_mode_summary: str = "单行模式：请求 {REQUESTED} 行，纯文本兜底 {FALLBACK} 行，失败 {FAILED} 行，解析失败 {MISMATCH} 行"
    translator_task_success: str = "任务耗时 {TIME} 秒，文本行数 {LINES} 行，输入消耗 {PT} Tokens，输出消耗 {CT} Tokens"
    translator_too_many_task: str = "实时任务数较多，暂时停止显示详细结果以提升性能 …"
    translator_no_items: str = "没有找到需要翻译的数据，请确认输入文件与项目设置是否正确 …"
    translator_running: str = "任务正在执行中，请稍后再试 …"
    file_checker_kana: str = "已完成假名残留检查，未发现异常条目 …"
    file_checker_kana_full: str = "已完成假名残留检查，发现 {COUNT} 个异常条目，占比为 {PERCENT} %，结果已写入 [green]{TARGET}[/] …"
    file_checker_hangeul: str = "已完成谚文残留检查，未发现异常条目 …"
    file_checker_hangeul_full: str = "已完成谚文残留检查，发现 {COUNT} 个异常条目，占比为 {PERCENT} %，结果已写入 [green]{TARGET}[/] …"
    file_checker_text_preserve: str = "已完成文本保护检查，未发现异常条目 …"
    file_checker_text_preserve_full: str = "已完成文本保护检查，发现 {COUNT} 个异常条目，占比为 {PERCENT} %，结果已写入 [green]{TARGET}[/] …"
    file_checker_text_preserve_alert_key: str = "____提醒____"
    file_checker_text_preserve_alert_value: str = "本文件内列出的是文本保护 **可能** 未生效的条目，请结合上下文语境进行实际判断！"
    file_checker_similarity: str = "已完成相似度异常检查，未发现异常条目 …"
    file_checker_similarity_full: str = "已完成相似度异常检查，发现 {COUNT} 个异常条目，占比为 {PERCENT} %，结果已写入 [green]{TARGET}[/] …"
    file_checker_similarity_alert_key: str = "____提醒____"
    file_checker_similarity_alert_value: str = "本文件内列出的是 **可能** 存在相似度较高情况的条目，请结合上下文语境进行实际判断！"
    file_checker_glossary: str = "已完成未生效术语检查，未发现异常条目 …"
    file_checker_glossary_full: str = "已完成未生效术语检查，发现 {COUNT} 个异常条目，占比为 {PERCENT} %，结果已写入 [green]{TARGET}[/] …"
    file_checker_mixed_translation: str = "已完成混合翻译检查，未发现异常条目 …"
    file_checker_mixed_translation_full: str = "已完成混合翻译检查，发现 {COUNT} 个异常条目，占比为 {PERCENT} %，结果已写入 [green]{TARGET}[/] …"
    platofrm_tester_key: str = "正在测试密钥"
    platofrm_tester_messages: str = "任务提示词："
    platofrm_tester_response_think: str = "模型思考内容："
    platofrm_tester_response_result: str = "模型返回结果："
    platofrm_tester_result: str = "共测试 {COUNT} 个接口，成功 {SUCCESS} 个，失败 {FAILURE} 个 …"
    platofrm_tester_result_failure: str = "失败的密钥："
    platofrm_tester_running: str = "任务正在执行中，请稍后再试 …"
    response_checker_unknown: str = "未知"
    response_checker_fail_data: str = "数据结构错误"
    response_checker_fail_line_count: str = "行数不一致"
    response_checker_line_error_kana: str = "假名残留"
    response_checker_line_error_hangeul: str = "谚文残留"
    response_checker_line_error_fake_reply: str = "伪回复残留"
    response_checker_line_error_empty_line: str = "存在空行"
    response_checker_line_error_mixed_language: str = "中英混杂残留"
    response_checker_line_error_similarity: str = "较高相似度"
    response_checker_line_error_degradation: str = "发生退化现象"
    response_decoder_glossary_by_json: str = "术语数据 -> 反序列化，共 {COUNT} 条"
    response_decoder_glossary_by_rule: str = "术语数据 -> 拆分后规则解析，共 {COUNT} 条"
    response_decoder_translation_by_json: str = "翻译数据 -> 反序列化，共 {COUNT} 条"
    response_decoder_translation_by_rule: str = "翻译数据 -> 拆分后规则解析，共 {COUNT} 条"

    # 应用设置
    app_update_group_title: str = "关于与更新"
    app_update_group_description: str = "查看当前版本、检查并安装更新"
    app_update_current_version: str = "当前版本"
    app_update_check: str = "检查更新"
    app_update_checking: str = "检查中…"
    app_update_status_not_checked: str = "尚未检查更新"
    app_update_status_check_failed: str = "检查更新失败，请重试"
    app_update_status_latest: str = "已是最新版本"
    app_update_status_new: str = "发现新版本 {VERSION}"
    app_update_status_downloading: str = "正在下载 {DOWNLOADED} / {TOTAL}"
    app_update_status_downloaded: str = "下载完成，重启后生效"
    app_update_view_details: str = "查看详情"
    app_update_cancel: str = "取消"
    app_update_cancelling: str = "正在取消…"
    app_update_install: str = "立即重启并安装"
    app_update_install_busy: str = "当前有任务正在运行，安装更新会中断任务并重启应用，确定继续吗"
    app_update_changelog_title: str = "更新日志"
    app_update_changelog_description: str = "查看版本变化与修复记录"
    app_update_changelog_action: str = "查看更新日志"
    app_update_details_title: str = "发现新版本 {VERSION}"
    app_update_notes_empty: str = "此版本暂无更新说明"
    app_update_release_metadata: str = "安装包 {SIZE} · 发布于 {DATE}"
    app_update_size_unknown: str = "大小未知"
    app_update_date_unknown: str = "日期未知"
    app_update_download: str = "下载更新"
    app_update_check_latest_toast: str = "当前已是最新版本"
    app_update_check_failure: str = "检查更新失败："
    app_update_cancelled: str = "已取消下载"
    toast_merged_count: str = "（×{}）"
    app_changelog_title: str = "更新日志"
    app_changelog_empty: str = "暂无更新日志"
    app_changelog_available: str = "可更新到 {VERSION}"
    app_changelog_open_browser: str = "在浏览器打开完整记录"
    app_settings_page_startup_sound_title: str = "启动音效"
    app_settings_page_startup_sound_content: str = "启用后，应用启动时会播放提示音（默认关闭）"
    app_settings_page_language_title: str = "应用语言"
    app_settings_page_language_content: str = "选择应用界面语言，更改将在重启应用后生效"
    app_settings_page_language_zh: str = "简体中文"
    app_settings_page_language_en: str = "English"
    app_settings_page_expert_title: str = "专家模式"
    app_settings_page_expert_content: str = "启用此功能后，将显示更多日志信息并提供更多高级设置选项（将在应用重启后生效）"
    app_settings_page_font_hinting_title: str = "字体优化"
    app_settings_page_font_hinting_content: str = "启用此功能后，应用内 UI 字体的边缘渲染将更加圆润（将在应用重启后生效）"
    app_settings_page_scale_factor_title: str = "全局缩放比例"
    app_settings_page_scale_factor_content: str = "启用此功能后，应用界面将按照所选比例进行缩放（将在应用重启后生效）"
    app_settings_page_proxy_url: str = "示例 - http://127.0.0.1:7890"
    app_settings_page_proxy_url_title: str = "网络代理"
    app_settings_page_proxy_url_content: str = "启用此功能后，将使用设置的代理地址发送网络请求（将在应用重启后生效）"
    app_settings_page_close: str = "应用即将关闭，请确认 …"

    # 接口管理
    platform_page_api_test_result: str = "接口测试结果：成功 {SUCCESS} 个，失败 {FAILURE} 个 …"
    platform_page_api_activate: str = "激活接口"
    platform_page_api_edit: str = "编辑接口"
    platform_page_api_args: str = "编辑参数"
    platform_page_api_test: str = "测试接口"
    platform_page_api_delete: str = "删除接口"
    platform_page_widget_add_title: str = "接口列表"
    platform_page_widget_add_content: str = "在此添加和管理兼容 Google、OpenAI、Anthropic、DeepL、DeepLX 的翻译接口"
    platform_page_active_hint: str = "当前激活接口：{NAME}"
    platform_page_active_none: str = "尚未设置激活接口"
    platform_page_empty_title: str = "暂无接口"
    platform_page_empty_content: str = "点击右上角「添加」按钮创建第一个接口"
    platform_page_group_local_title: str = "本地模型"
    platform_page_group_local_content: str = "本地部署或运行在局域网中的模型接口"
    platform_page_group_machine_title: str = "传统机翻"
    platform_page_group_machine_content: str = "DeepL 与 DeepLX 等非 LLM 翻译接口"
    platform_page_group_online_title: str = "在线大模型"
    platform_page_group_online_content: str = "各平台提供的在线大模型接口"
    platform_page_group_custom_title: str = "自定义接口"
    platform_page_group_custom_content: str = "第三方或自行配置的接口"

    # 接口编辑
    platform_edit_page_name: str = "请输入接口名称 …"
    platform_edit_page_name_title: str = "接口名称"
    platform_edit_page_name_content: str = "请输入接口名称，仅用于应用内显示，无实际作用"
    platform_edit_page_api_url: str = "请输入接口地址 …"
    platform_edit_page_api_url_title: str = "接口地址"
    platform_edit_page_api_url_content: str = "请输入接口地址，请注意辨别结尾是否需要添加 /v1"
    platform_edit_page_api_key: str = "请输入接口密钥 …"
    platform_edit_page_api_key_title: str = "接口密钥"
    platform_edit_page_api_key_content: str = "请输入接口密钥，例如 sk-d0daba12345678fd8eb7b8d31c123456，填入多个密钥可以轮询使用，每行一个"
    platform_edit_page_api_key_clear_failed: str = "凭据库清理失败，原密钥仍保留"
    platform_edit_page_api_key_save_failed: str = "接口密钥保存失败，请重试"
    platform_edit_page_thinking_title: str = "思考等级"
    platform_edit_page_thinking_content: str = "设置模型思考等级（OFF/LOW/MEDIUM/HIGH/MAX），仅对支持思考模式的模型生效"
    platform_edit_page_thinking_off: str = "关闭"
    platform_edit_page_thinking_low: str = "低"
    platform_edit_page_thinking_medium: str = "中"
    platform_edit_page_thinking_high: str = "高"
    platform_edit_page_thinking_max: str = "最高"
    platform_edit_page_model: str = "请输入模型名称 …"
    platform_edit_page_model_title: str = "模型名称"
    platform_edit_page_model_content: str = "当前使用的模型为 {MODEL}"
    platform_edit_page_model_edit: str = "手动输入"
    platform_edit_page_model_sync: str = "在线获取"

    # 参数编辑
    args_edit_page_top_p_title: str = "top_p"
    args_edit_page_top_p_content: str = "请谨慎设置，错误的值可能导致结果异常或者请求报错"
    args_edit_page_temperature_title: str = "temperature"
    args_edit_page_temperature_content: str = "请谨慎设置，错误的值可能导致结果异常或者请求报错"
    args_edit_page_presence_penalty_title: str = "presence_penalty"
    args_edit_page_presence_penalty_content: str = "请谨慎设置，错误的值可能导致结果异常或者请求报错"
    args_edit_page_frequency_penalty_title: str = "frequency_penalty"
    args_edit_page_frequency_penalty_content: str = "请谨慎设置，错误的值可能导致结果异常或者请求报错"
    args_edit_page_document_link: str = "点击查看文档"

    # 模型列表
    model_list_page_title: str = "可用的模型列表"
    model_list_page_content: str = "点击选择要使用的模型"
    model_list_page_fail: str = "获取模型列表失败，请检查接口配置 …"

    # 项目设置
    project_page_source_language_title: str = "原文语言"
    project_page_source_language_content: str = "设置当前项目中输入文本的语言"
    project_page_target_language_title: str = "译文语言"
    project_page_target_language_content: str = "设置当前项目中输出文本的语言"
    project_page_input_folder_title: str = "输入文件夹"
    project_page_input_folder_content: str = "当前输入文件夹为"
    project_page_output_folder_title: str = "输出文件夹（不能与输入文件夹相同）"
    project_page_output_folder_content: str = "当前输出文件夹为"
    project_page_output_folder_open_on_finish_title: str = "任务完成时打开输出文件夹"
    project_page_output_folder_open_on_finish_content: str = "启用此功能后，将在任务完成时自动打开输出文件夹"
    project_page_traditional_chinese_title: str = "使用繁体输出中文"
    project_page_traditional_chinese_content: str = "启用此功能后，在译文语言设置为中文时，将使用繁体字形输出中文文本"

    # 开始翻译
    translation_page_status_idle: str = "无任务"
    translation_page_status_testing: str = "测试中"
    translation_page_status_translating: str = "翻译中"
    translation_page_status_stopping: str = "停止中"
    translation_page_status_polishing: str = "AI 润色中"
    translation_page_status_proofreading: str = "AI 校对中"
    translation_page_status_stopping_polishing: str = "正在停止 AI 润色"
    translation_page_status_stopping_proofreading: str = "正在停止 AI 校对"
    translation_page_indeterminate_saving: str = "缓存文件保存中 …"
    translation_page_indeterminate_stoping: str = "正在停止翻译任务 …"
    translation_page_card_time: str = "累计时间"
    translation_page_card_remaining_time: str = "剩余时间"
    translation_page_card_line: str = "翻译行数"
    translation_page_card_remaining_line: str = "剩余行数"
    translation_page_card_speed: str = "平均速度"
    translation_page_card_token: str = "累计消耗"
    translation_page_card_token_input: str = "输入令牌"
    translation_page_card_token_output: str = "输出令牌"
    translation_page_card_token_tooltip: str = "点击切换输入/输出"
    translation_page_card_task: str = "实时任务数"
    translation_page_alert_pause: str = "停止的翻译任务可以随时继续翻译，是否确定停止任务 … ？"
    translation_page_continue: str = "继续任务"
    translation_page_export: str = "导出任务数据"
    translation_page_export_tooltip: str = "导出译文文件"
    translation_page_reinject_cache: str = "从缓存重新注入"
    translation_page_reinject_cache_tooltip: str = "将缓存中的译文重新写回输出目录"
    translation_page_reinject_cache_confirm: str = "将从缓存重新写回译文文件，是否继续？"
    translation_page_reinject_cache_success: str = "缓存重新注入完成"
    translation_page_reinject_cache_no_cache: str = "未找到缓存数据，请先翻译"
    translation_page_timer: str = "请设置延迟启动前要等待的时间"
    translation_page_preflight_missing_assets_title: str = "当前项目没有可用资产"
    translation_page_preflight_missing_assets_content: str = "未找到已启用且有效的世界观、角色卡、术语或禁翻项。可以先打开工作台完善项目资产，也可以仍然继续本次翻译。"
    translation_page_preflight_open_workbench: str = "打开工作台"
    translation_page_preflight_continue: str = "仍然继续"
    translation_page_preflight_load_error: str = "读取当前项目资产失败，翻译尚未启动：{ERROR}"
    translation_page_preflight_workbench_unavailable: str = "无法打开工作台，请从侧边栏进入角色/世界观工作台。"

    # 校对任务
    proofreading_page_load: str = "载入"
    proofreading_page_save: str = "保存"
    proofreading_page_save_tooltip: str = "快捷键 Ctrl + S"
    proofreading_page_export: str = "导出"
    proofreading_page_search: str = "搜索"
    proofreading_page_filter: str = "筛选"
    proofreading_page_retranslate: str = "重新翻译"
    proofreading_page_confirm_translation: str = "确认译文无误"
    proofreading_page_confirm_selected_translations: str = "确认选中译文无误"
    proofreading_page_confirm_translation_done: str = "已确认 {COUNT} 条译文无误，请点击保存"
    proofreading_page_copy_src: str = "复制原文"
    proofreading_page_copy_src_done: str = "已复制原文到剪贴板"
    proofreading_page_copy_dst: str = "复制译文"
    proofreading_page_copy_dst_done: str = "已复制译文到剪贴板"
    proofreading_page_save_success: str = "数据已保存"
    proofreading_page_export_success: str = "导出完成"
    proofreading_page_export_failed: str = "导出失败"
    proofreading_page_export_confirm: str = "确定要导出译文文件吗？"
    proofreading_page_export_tooltip: str = "导出译文文件\n先保存数据，然后生成译文文件"
    proofreading_page_col_src: str = "原文"
    proofreading_page_col_dst: str = "译文"
    proofreading_page_col_status: str = "状态"
    proofreading_page_no_cache: str = "未找到缓存文件，请先执行翻译任务"
    proofreading_page_load_failed: str = "缓存文件读取失败"
    proofreading_page_save_failed: str = "保存失败"
    proofreading_page_retranslate_confirm: str = "确定要重新翻译此条目吗？"
    proofreading_page_retranslate_failed: str = "翻译失败，请重试"
    proofreading_page_retranslate_success: str = "翻译完成"
    proofreading_page_batch_replace: str = "批量替换"
    proofreading_page_batch_retranslate: str = "批量重译"
    proofreading_page_batch_reset_translation: str = "批量重置"
    proofreading_page_batch_no_selection: str = "请先选择要操作的条目"
    proofreading_page_batch_replace_action: str = "批量替换"
    proofreading_page_batch_replace_find: str = "查找内容"
    proofreading_page_batch_replace_with: str = "替换为"
    proofreading_page_batch_replace_options: str = "替换选项"
    proofreading_page_batch_replace_regex: str = "使用正则"
    proofreading_page_batch_replace_case_sensitive: str = "区分大小写"
    proofreading_page_batch_replace_scope: str = "替换范围"
    proofreading_page_batch_replace_scope_selected: str = "仅选中条目（{COUNT}）"
    proofreading_page_batch_replace_scope_filtered: str = "当前筛选结果（{COUNT}）"
    proofreading_page_batch_replace_empty_keyword: str = "请先输入查找内容"
    proofreading_page_batch_replace_invalid_regex: str = "正则表达式无效"
    proofreading_page_batch_replace_done: str = "批量替换完成：变更 {N} 条"
    proofreading_page_batch_replace_no_change: str = "没有需要替换的内容"
    proofreading_page_batch_retranslate_confirm: str = "确定要批量重新翻译选中的 {COUNT} 条吗？"
    proofreading_page_batch_retranslate_done: str = "批量重译完成：成功 {SUCCESS} 条，失败 {FAILURE} 条"
    proofreading_page_batch_reset_translation_confirm: str = "确定要批量重置选中的 {COUNT} 条吗？"
    proofreading_page_batch_reset_translation_done: str = "批量重置完成：变更 {N} 条"
    proofreading_page_warning_tooltip_title: str = "结果检查"
    proofreading_page_filter_warning_type: str = "结果检查"
    proofreading_page_filter_status: str = "翻译状态"
    proofreading_page_filter_file: str = "所属文件"
    proofreading_page_filter_glossary_terms: str = "术语明细"
    proofreading_page_status_none: str = "未翻译"
    proofreading_page_status_processed: str = "已完成"
    proofreading_page_status_polished: str = "已润色"
    proofreading_page_status_processed_in_past: str = "历史完成"
    proofreading_page_page_info: str = "第 {CURRENT} / {TOTAL} 页"
    proofreading_page_warning_kana: str = "假名残留"
    proofreading_page_warning_hangeul: str = "谚文残留"
    proofreading_page_warning_text_preserve: str = "文本保护失效"
    proofreading_page_warning_similarity: str = "相似度过高"
    proofreading_page_warning_glossary: str = "术语表未生效"
    proofreading_page_warning_retry: str = "重试次数达阈值"
    proofreading_page_filter_select_all: str = "全选"
    proofreading_page_filter_no_warning: str = "无警告"
    proofreading_page_filter_clear: str = "清除"
    proofreading_page_filter_no_glossary_error: str = "没有术语表警告"
    proofreading_page_filter_export: str = "导出报告"
    proofreading_page_filter_export_tooltip: str = "导出筛选结果到文件"
    proofreading_page_filter_export_success: str = "筛选结果已导出"
    proofreading_page_filter_export_failed: str = "筛选结果导出失败"
    proofreading_page_indeterminate_loading: str = "加载数据中 …"
    proofreading_page_indeterminate_saving: str = "保存数据中 …"
    proofreading_page_indeterminate_exporting: str = "导出数据中 …"
    proofreading_page_ai_polish: str = "AI 润色选中译文"
    proofreading_page_ai_polish_tooltip: str = "优化选中译文的表达、风格和角色语气"
    proofreading_page_ai_proofread: str = "AI 校对选中译文"
    proofreading_page_ai_proofread_tooltip: str = "按术语、占位符和质量警告校对选中译文"
    proofreading_page_quality_report: str = "质量检查报告"
    proofreading_page_quality_report_tooltip: str = "查看检测到的问题；可直接选择条目并启动 AI 校对"
    proofreading_page_quality_cancel: str = "停止 AI 任务"
    proofreading_page_quality_cancel_tooltip: str = "立即取消当前 AI 请求；已完成批次会保留"
    proofreading_page_quality_no_polishable: str = "选中条目中没有可润色的已翻译内容"
    proofreading_page_quality_no_proofreadable: str = "选中条目中没有可校对的译文"
    proofreading_page_quality_confirm_polish: str = "确定要润色选中的 {COUNT} 条译文吗？"
    proofreading_page_quality_confirm_proofread: str = "确定要校对选中的 {COUNT} 条译文吗？"
    proofreading_page_quality_start_failed: str = "质量任务启动失败，请检查翻译快照和平台配置"
    proofreading_page_quality_progress: str = "{TASK}：已处理 {PROCESSED}/{TOTAL}，更新 {UPDATED} 条，失败 {FAILED} 条"
    proofreading_page_quality_done: str = "{TASK}完成：更新 {UPDATED} 条，失败 {FAILED} 条，跳过 {SKIPPED} 条"
    proofreading_page_quality_cancelled: str = "质量任务已停止，已完成的批次已保存"
    proofreading_page_quality_cancelling: str = "正在停止质量任务 …"
    proofreading_page_quality_report_title: str = "翻译质量检查报告"
    proofreading_page_quality_report_failed: str = "失败条目"
    proofreading_page_quality_report_fallback: str = "回退条目"
    proofreading_page_quality_report_alignment: str = "索引/行数错位"
    proofreading_page_quality_report_error_types: str = "错误类型：{ERRORS}"
    proofreading_page_quality_report_items: str = "选择要校对的条目"
    proofreading_page_quality_report_empty: str = "当前缓存没有记录可定位的质量失败条目"
    proofreading_page_quality_report_proofread: str = "校对所选条目"
    translation_page_status_quality: str = "质量处理中"
    translation_page_status_agent: str = "Agent 操作中"

    # Agent 页面
    agent_page_title: str = "Agent 助手"
    agent_page_description: str = "当前项目"
    agent_page_project_unset: str = "未设置项目"
    agent_page_project_context: str = "{name} · {language}"
    agent_page_platform: str = "Agent 接口"
    agent_page_platform_unset: str = "未设置 Agent 接口"
    agent_page_platform_saved: str = "Agent 接口已保存"
    agent_page_refresh: str = "刷新"
    agent_page_input_placeholder: str = "描述你要处理的项目任务 …"
    agent_page_send: str = "发送"
    agent_page_stop: str = "停止"
    agent_page_running: str = "正在处理 …"
    agent_page_cancelled: str = "已请求停止"
    agent_page_done: str = "已完成"
    agent_page_failed: str = "执行失败"
    agent_page_assistant_label: str = "Agent"
    agent_page_thinking_process: str = "思考过程"
    agent_page_user_label: str = "你"
    agent_page_error_label: str = "错误"
    agent_page_empty_title: str = "新任务"
    agent_page_empty_description: str = "当前会话尚无内容"
    agent_page_suggestion_project: str = "检查项目并告诉我下一步"
    agent_page_suggestion_rpa: str = "列出项目中的 RPA 文件"
    agent_page_suggestion_errors: str = "扫描项目脚本错误"
    agent_page_suggestion_old_new: str = "优化未生效的 old/new 译文"
    agent_page_suggestion_project_desc: str = "汇总解包、翻译、资产与质量状态"
    agent_page_suggestion_rpa_desc: str = "列出 game 目录中的 RPA 归档文件"
    agent_page_suggestion_errors_desc: str = "扫描常见脚本错误，不修改任何文件"
    agent_page_suggestion_old_new_desc: str = "翻译完成后生成运行时替换补丁"
    agent_page_tool_expand: str = "查看详情"
    agent_page_tool_running: str = "执行中"
    agent_page_tool_done: str = "已完成"
    agent_page_tool_failed: str = "失败"
    agent_page_tool_calling: str = "正在调用工具"
    agent_page_tool_prefix: str = "工具"
    agent_page_tool_set_project: str = "设定项目"
    agent_page_tool_get_project_info: str = "读取项目信息"
    agent_page_tool_inspect_translation_project: str = "检查项目翻译状态"
    agent_page_tool_list_rpa_files: str = "查找 RPA 文件"
    agent_page_tool_scan_script_errors: str = "扫描脚本错误"
    agent_page_tool_unpack_rpa_files: str = "解包 RPA 文件"
    agent_page_tool_optimize_old_new_translations: str = "优化 old/new 译文"
    agent_page_action_open_translation: str = "进入翻译页面"
    agent_page_action_one_key_translate: str = "一键开始翻译"
    agent_page_action_continue_translation: str = "继续翻译"
    agent_page_action_open_workbench: str = "打开角色 / 世界观工作台"
    agent_page_action_open_toolbox: str = "打开 Ren'Py 工具箱"
    agent_page_action_unpack_rpa_prompt: str = "解包当前项目中的 RPA 文件"
    agent_page_one_key_unavailable: str = "当前无法启动一键翻译，请检查项目状态后重试"
    agent_page_confirmation_title: str = "确认解包 RPA"
    agent_page_confirmation_generic: str = "Agent 即将执行 {tool}，是否继续？"
    agent_page_waiting_confirmation: str = "等待确认"
    agent_page_unpack_confirmation: str = (
        "即将解包当前项目中的 {count} 个 RPA 文件：\n{game_dir}\n\n"
        "解包结果会直接写入 game 目录，并可能覆盖同名文件；原 RPA 文件会保留。是否继续？"
    )
    agent_page_old_new_confirmation_title: str = "确认生成 old/new 替换补丁"
    agent_page_old_new_confirmation: str = (
        "当前语言目录：\n{tl_dir}\n\n"
        "有效 old/new：{old_new_count} 条\n"
        "合并现有补漏：{supplement_count} 条\n"
        "最终替换：{total_count} 条\n"
        "跳过冲突原文：{conflict_count} 条\n\n"
        "将按原文从长到短生成运行时替换代码：\n{output_path}\n\n"
        "若已有自动补全 Hook，会先备份再覆盖。是否继续？"
    )
    agent_page_new_task: str = "新任务"
    agent_page_round: str = "第 {round} 轮"
    agent_page_topbar_api: str = "接口"
    agent_page_settings_title: str = "Agent 设置"
    agent_page_settings_refresh: str = "刷新接口列表"
    agent_page_settings_unpack_confirm: str = "解包 RPA 前确认"
    agent_page_unpack_dont_ask: str = "以后自动解包，不再询问"
    agent_page_retry: str = "点击重试"
    agent_page_user_avatar: str = "你"
    agent_page_send_hint: str = "Ctrl + Enter 发送"
    agent_page_copy: str = "复制"
    agent_page_copied: str = "已复制到剪贴板"
    agent_page_stopped_hint: str = "已停止生成"
    agent_page_platform_changed_hint: str = "已切换 Agent 接口，当前会话上下文仍属于原接口；如需全新上下文请点击「新任务」。"
    agent_page_tool_detail_truncated: str = "结果过长，仅显示前 {shown} 个字符（共 {total} 个），完整内容见悬停提示。"

    # Agent 工具
    agent_tool_set_project_description: str = (
        "设定用户明确提供的 Ren'Py 项目目录。成功后返回规范项目根、game 目录和语言。"
    )
    agent_tool_project_path_description: str = "用户在对话中明确提供的项目路径。"
    agent_tool_get_project_info_description: str = (
        "读取当前已设定的项目目录和语言；未设定时返回 PROJECT_NOT_SET。"
    )
    agent_tool_inspect_translation_project_description: str = (
        "只读检查当前项目的脚本、RPA、翻译缓存、工作台资产、质量问题和 old/new 状态，"
        "返回稳定的下一步建议；不启动翻译，也不修改文件。"
    )
    agent_tool_list_rpa_files_description: str = (
        "列出当前项目 game 目录中的 RPA 文件。目录由服务端配置注入。"
    )
    agent_tool_scan_script_errors_description: str = (
        "扫描当前项目 game 目录中的 Ren'Py 脚本错误，不修改文件。"
    )
    agent_tool_unpack_rpa_files_description: str = (
        "解包当前项目 game 目录中的全部 RPA 文件。目录由服务端注入，"
        "执行前必须由用户确认同名文件覆盖风险，原 RPA 文件始终保留。"
    )
    agent_tool_optimize_old_new_translations_description: str = (
        "翻译完成后，读取当前语言目录的有效 old/new 译文，按原文从长到短生成 "
        "replace_text 运行时补丁，以覆盖追加攻略文本、颜色标签等导致的完整字符串失配。"
    )
    agent_project_inspection_complete: str = (
        "项目体检完成：RPY {rpy_count}、RPYC {rpyc_count}、RPA {rpa_count}；"
        "缓存条目 {item_count}，待翻译 {untranslated_count}。建议下一步：{next_action}。"
    )
    agent_inspection_action_unpack_rpa: str = "先解包 RPA 文件"
    agent_inspection_action_decompile_scripts: str = "先反编译 RPYC 脚本"
    agent_inspection_action_repair_cache: str = "先检查或修复翻译缓存"
    agent_inspection_action_review_workbench: str = "先审核并应用工作台草稿"
    agent_inspection_action_start_translation: str = "进入翻译页面开始翻译"
    agent_inspection_action_continue_translation: str = "继续未完成的翻译"
    agent_inspection_action_review_quality: str = "先处理翻译质量问题"
    agent_inspection_action_review_translation: str = "检查并应用翻译结果"
    agent_inspection_action_check_project_files: str = "检查项目目录中是否有可处理脚本"
    agent_system_prompt: str = (
        "你是 RenpyBox 的项目助手。只使用当前提供的工具完成任务。\n"
        "安全规则：只有用户明确提供路径时才能调用 set_project(path)；其他工具没有路径参数，"
        "必须让服务端从当前项目配置注入目录。不要猜测、拼接或替换任何目录。\n"
        "如果工具返回 PROJECT_NOT_SET，明确告诉用户尚未设定项目目录并询问游戏路径；"
        "用户提供路径后调用 set_project，再继续原任务。\n"
        "当用户询问项目现状、翻译进度或下一步时，优先调用 inspect_translation_project；"
        "该工具只读，按返回的 next_action_code 解释建议，不要声称已经执行建议操作。\n"
        "unpack_rpa_files 会写入当前 game 目录，只有用户在界面确认覆盖风险后才能执行；"
        "不要声称可以删除 RPA、指定输出目录或中止已经启动的外部解包进程。"
        "界面操作按钮发出的明确请求应直接调用对应工具；确认由界面的确认/取消按钮处理，"
        "不要在回复中重复用文字询问。回复不要使用 Emoji 或彩色 Unicode 状态图标，"
        "状态和操作图标由界面统一显示。"
        "翻译本身由翻译页面完成，不要使用 Agent 重新翻译；翻译已应用后，只有用户要求修复运行时"
        "未生效的 old/new、选项攻略尾注或颜色标记时，才调用 optimize_old_new_translations，且必须确认。"
        "工具结果中的完整详情由界面展示，你的回复只总结关键结果。"
    )

    # Agent 运行时
    agent_request_schema_only: str = "仅用于请求 schema。"
    agent_request_unsupported_platform: str = "当前接口不支持 Agent 工具调用，请在 Agent 设置中选择 OpenAI、Anthropic 或 Google 接口。"
    agent_request_unsupported_format: str = "当前接口格式不支持 Agent 工具调用。"
    agent_request_no_tools: str = "没有可用的 Agent 工具。"
    agent_request_cancelled: str = "Agent 请求已取消。"
    agent_request_bad_request: str = "模型拒绝了 Agent 请求参数。"
    agent_request_failed: str = "Agent 请求失败，请检查接口配置或网络。"
    agent_tool_arguments_must_be_object: str = "工具参数必须是 JSON 对象。"
    agent_tool_undeclared_arguments: str = "包含未声明参数：{names}。"
    agent_tool_missing_arguments: str = "缺少必填参数：{names}。"
    agent_tool_argument_must_be_string: str = "参数 {name} 必须是字符串。"
    agent_tool_argument_must_be_object: str = "参数 {name} 必须是对象。"
    agent_tool_unknown: str = "未知工具：{name}"
    agent_tool_confirmation_required: str = "该操作需要用户确认。"
    agent_tool_confirmation_stale: str = "确认上下文已失效，请重新确认后再试。"
    agent_tool_engine_busy: str = "引擎正在运行，当前不能执行此操作。"
    agent_tool_invalid_result: str = "工具返回了无效结果。"
    agent_tool_failed_logged: str = "工具执行失败，详细信息已写入日志。"
    agent_tool_cancelled: str = "操作已取消，未执行工具。"
    agent_api_unset: str = "尚未设定 Agent 接口，请先在 Agent 页面选择 OpenAI、Anthropic 或 Google 接口。"
    agent_api_missing: str = "Agent 接口配置不存在，请重新选择接口。"
    agent_task_empty: str = "请输入要执行的任务。"
    agent_api_not_set: str = "Agent 接口未设置。"
    agent_reply_empty: str = "Agent 没有返回可显示的内容。"
    agent_confirmation_timeout: str = "等待确认超时，未执行工具。"
    agent_project_changed: str = "项目内容已变化，请重新确认后再试。"
    agent_max_iterations: str = "Agent 达到最大工具调用轮数，已停止继续执行。"
    agent_project_not_set_ask: str = "尚未设定项目目录，请先询问用户游戏所在目录，再调用 set_project。"
    agent_project_not_set: str = "尚未设定项目目录，请先设定项目。"
    agent_project_path_empty: str = "项目路径不能为空。"
    agent_project_path_invalid: str = "路径不像有效的 Ren'Py 项目（需要 game 或 tl 目录）。"
    agent_project_game_not_found: str = "无法定位存在的 game 目录，项目目录未写入配置。"
    agent_project_set: str = "已设定项目：{project_root}（语言：{language}）"
    agent_project_current: str = "当前项目：{project_root}（语言：{language}）"
    agent_rpa_not_found: str = "当前项目没有找到 RPA 文件。"
    agent_rpa_found: str = "当前项目找到 {count} 个 RPA 文件：{files}"
    agent_scan_no_errors: str = "脚本扫描完成，未发现错误。"
    agent_scan_errors: str = "脚本扫描完成，发现 {total} 个问题，已返回前 {returned} 个。"
    agent_unpack_project_changed: str = "项目目录已变化，请重新确认后再试。"
    agent_unpack_complete: str = "RPA 解包完成，共处理 {count} 个归档；原 RPA 文件已保留。"
    agent_unpack_failed: str = "RPA 解包失败，请查看日志了解详情。"
    agent_old_new_translation_not_found: str = "当前语言目录没有找到可用于优化的有效 old/new 译文。"
    agent_old_new_optimization_complete: str = "old/new 运行时替换补丁已生成，共 {count} 条：{output_path}"

    # 基础设置
    basic_settings_page_max_workers_title: str = "并发任务阈值"
    basic_settings_page_max_workers_content: str = (
        "同时执行的任务数量的最大值"
        "<br>"
        "默认 16；合理设置可以显著加快任务的完成速度，请参考 API 平台的文档进行设置，0 = 自动"
        ""
        ""
    )
    basic_settings_page_rpm_threshold_title: str = "每分钟任务数量阈值"
    basic_settings_page_rpm_threshold_content: str = (
        "每分钟执行的任务总数量的最大值，即 <font color='darkgoldenrod'><b>RPM</b></font> 阈值"
        "<br>"
        "部分平台会对网络请求的速率进行限制，请参考 API 平台的文档进行设置，0 = 无限制"
        ""
        ""
    )
    basic_settings_page_token_threshold_title: str = "任务行数阈值"
    basic_settings_page_token_threshold_content: str = "每个任务所包含的文本的最大行数（建议 5-15 行，行数越少翻译越稳定）"
    basic_settings_page_request_timeout_title: str = "超时时间阈值"
    basic_settings_page_request_timeout_content: str = (
        "发起请求时等待模型回复的最长时间（秒），超时仍未收到回复，则会判断为任务失败"
        ""
        ""
    )
    basic_settings_page_max_round_title: str = "任务轮次阈值"
    basic_settings_page_max_round_content: str = "当完成一轮任务后，将在新的轮次中对失败的任务进行重试，直到全部完成或达到轮次阈值"

    # 专家设置
    expert_settings_page_preceding_lines_threshold: str = "参考上文行数阈值"
    expert_settings_page_preceding_lines_threshold_desc: str = "每个翻译任务最多可携带的参考上文的行数，默认禁用"
    expert_settings_page_preceding_disable_on_local: str = "本地接口启用参考上文"
    expert_settings_page_preceding_disable_on_local_desc: str = "本地模型性能较差，参考上文功能大部分时候是负面效果，默认禁用"
    expert_settings_page_single_line_translation: str = "单行翻译模式"
    expert_settings_page_single_line_translation_desc: str = (
        "启用后，每次请求只提交一行原文，并允许模型直接返回纯文本译文"
        "<br>"
        "适合腾讯 hy1.5 等速度快但批量 JSONLINE 格式容易错位的小模型；会增加请求次数，但可显著降低行数不一致"
    )
    expert_settings_page_structured_output: str = "结构化输出"
    expert_settings_page_structured_output_desc: str = (
        "启用后，通过 API 级别的 JSON 格式约束（response_format）保证输出结构合法"
        "<br>"
        "可减少强模型的解析失败；若 API 提供商不支持此功能，请关闭作为保底"
    )
    expert_settings_page_clean_ruby: str = "清理原文中的注音文本"
    expert_settings_page_clean_ruby_desc: str = (
        "移除注音上标中的注音部分，仅保留正文部分，默认启用"
        "<br>"
        "文本中的注音上标通常不能被模型正确理解，进行清理可以提升翻译质量，支持的注音格式包括但不限于："
        "<br>"
        "• (漢字/かんじ) [漢字/かんじ] |漢字[かんじ]"
        "<br>"
        "• \\r[漢字,かんじ] \\rb[漢字,かんじ] [r_かんじ][ch_漢字] [ch_漢字]"
        "<br>"
        "• [ruby text=かんじ] [ruby text = かんじ] [ruby text=\"かんじ\"] [ruby text = \"かんじ\"]"
        ""
        ""
    )
    expert_settings_page_deduplication_in_trans: str = "T++ 项目文件中对重复文本去重"
    expert_settings_page_deduplication_in_trans_desc: str = "在T++ 项目文件（即 <font color='darkgoldenrod'><b>.trans</b></font> 文件）中，如有重复文本是否去重，默认启用"
    expert_settings_page_deduplication_in_bilingual: str = "双语输出文件中原文与译文一致的文本只输出一次"
    expert_settings_page_deduplication_in_bilingual_desc: str = "在字幕与电子书中，如目标文本的原文与译文一致是否只输出一次，默认启用"
    expert_settings_page_write_translated_name_fields_to_file: str = "将姓名字段译文写入输出文件"
    expert_settings_page_write_translated_name_fields_to_file_desc: str = (
        "部分 <font color='darkgoldenrod'><b>GalGame</b></font> 中，姓名字段数据与立绘、配音等资源文件绑定，翻译后会报错，此时可以关闭该功能，默认启用"
        "<br>"
        "支持格式："
        "<br>"
        "• RenPy 导出游戏文本（.rpy）"
        "<br>"
        "• VNTextPatch 或 SExtractor 导出带 name 字段的游戏文本（.json）"
        ""
        ""
    )
    expert_settings_page_auto_process_prefix_suffix_preserved_text: str = "自动处理前后缀的保护文本段"
    expert_settings_page_auto_process_prefix_suffix_preserved_text_desc: str = (
        "是否自动处理每个文本条目头尾命中保护规则的文本段，默认启用"
        "<br>"
        "• 启用后，头尾命中保护规则的文本段将被移除，翻译完成后再拼接回去"
        "<br>"
        "• 禁用后，会将完整的文本条目发送给模型翻译，可能会获得更完整的语义，但会降低文本保护效果"
    )
    expert_settings_page_honorific_placeholder_bridge: str = "称呼变量智能桥接"
    expert_settings_page_honorific_placeholder_bridge_desc: str = (
        "自动处理称呼 + 变量场景（如 Mr.[xx]），避免模型丢失变量并修正中文语序，默认启用"
        "<br>"
        "• 译前会将变量临时替换为结构化占位符，避免模型翻译或改写变量"
        "<br>"
        "• 译后会自动还原为原变量（如 [xx]先生），无需手工术语和搜索替换"
    )
    expert_settings_page_honorific_placeholder_titles: str = "称呼词列表（可自定义）"
    expert_settings_page_honorific_placeholder_titles_desc: str = (
        "用于识别“称呼 + 变量”结构的称呼词，可在下方表格中直接增删改，保存后立即生效"
    )
    expert_settings_page_honorific_placeholder_titles_placeholder: str = "示例：mr,mrs,dr,professor,master,captain,lord,sensei"
    expert_settings_page_honorific_placeholder_titles_column: str = "称呼词"
    expert_settings_page_honorific_placeholder_titles_select_delete: str = "请选择需要删除的行"
    expert_settings_page_honorific_placeholder_titles_reload_success: str = "已从配置重新加载称呼词"
    expert_settings_page_honorific_placeholder_titles_save_success: str = "已保存 {COUNT} 个称呼词"
    expert_settings_page_sakura_jsonline_retry_enable: str = "Sakura JSONLINE 解析失败时格式化重试"
    expert_settings_page_sakura_jsonline_retry_enable_desc: str = (
        "当 SakuraLLM 回复不是 JSONLINE 时，自动发起一次格式化重试，提高通过率"
    )
    expert_settings_page_result_checker_retry_count_threshold: str = "结果检查 - 重试次数达到阈值"
    expert_settings_page_result_checker_retry_count_threshold_desc: str = (
        "是否在结果检查报告里面输出 <font color='darkgoldenrod'><b>重试次数达到阈值</b></font> 的条目列表"
        "<br>"
        "• 在进行翻译结果检查时，重试达阈值后会放宽部分检查，但原文照抄、空译文等明显异常仍不会直接通过"
        "<br>"
        "• 通过此功能，就可以逐一确认这些条目的最终取值是否可靠"
    )

    # 质量类通用
    quality_import: str = "导入"
    quality_import_toast: str = "数据已导入 …"
    quality_export: str = "导出"
    quality_export_toast: str = "数据已导出到应用根目录 …"
    quality_save: str = "保存"
    quality_save_toast: str = "数据已保存 …"
    quality_merge_duplication: str = "已合并重复数据 …"
    quality_preset: str = "预设"
    quality_reset: str = "重置"
    quality_reset_toast: str = "数据已重置 …"
    quality_reset_alert: str = "是否确认重置为默认数据 … ？"
    quality_select_file: str = "选择文件"
    quality_select_file_type: str = "支持的数据格式 (*.json *.xlsx)"
    quality_delete_row: str = "删除行"
    quality_switch_regex: str = "切换正则模式"

    # 规则列
    rule_regex: str = "正则表达式"
    rule_regex_on: str = "当前状态：已启用"
    rule_regex_off: str = "当前状态：未启用"
    rule_case_sensitive: str = "大小写敏感"
    rule_case_sensitive_on: str = "当前状态：已启用"
    rule_case_sensitive_off: str = "当前状态：未启用"

    # 术语表
    glossary_page_head_title: str = "术语表"
    glossary_page_head_content: str = "通过在提示词中构建术语表来引导模型翻译，可实现统一翻译、矫正人称属性等功能"
    glossary_page_table_row_01: str = "原文"
    glossary_page_table_row_02: str = "译文"
    glossary_page_table_row_03: str = "描述"
    glossary_page_kg: str = "一键制作工具"

    # 文本保护
    text_preserve_page_head_title: str = "自定义文本保护规则"
    text_preserve_page_head_content: str = (
        "对文本中不需要翻译的代码段、控制字符、样式字符等文本进行保护，避免这些文本被错误的翻译"
        "<br>"
        "<font color='darkgoldenrod'><b>默认禁用</b></font>，启用前请仔细阅读 <font color='darkgoldenrod'><b>Wiki</b></font> 中的功能说明以确保充分理解使用方式"
        "<br>"
        "• 启用 - 根据本页中设置的 <font color='darkgoldenrod'><b>正则规则</b></font> 匹配对应的文本进行保护"
        "<br>"
        "• 禁用 - 自动判断文本格式与游戏引擎，智能选择合适的保护规则，在大部分内容中都可以取得较好的效果"
    )
    text_preserve_page_table_row_01: str = "规则"
    text_preserve_page_table_row_02: str = "备注（仅作备忘，无实际作用）"

    # 译前替换
    pre_translation_replacement_page_head_title: str = "译前替换"
    pre_translation_replacement_page_head_content: str = (
        "在翻译开始前，将原文中匹配的部分替换为指定的文本，执行的顺序为从上到下依次替换"
        "<br>"
        "对于 <font color='darkgoldenrod'><b>RPGMaker MV/MZ</b></font> 引擎的游戏："
        "<br>"
        "• 导入游戏目录的 <font color='darkgoldenrod'><b>data</b></font> 或者 <font color='darkgoldenrod'><b>www\\data</b></font> 文件夹内的 <font color='darkgoldenrod'><b>actors.json</b></font> 文件可以显著提升翻译质量"
        "<br>"
        "• 游戏中包含自定义姓名功能时需要进行特殊处理，请点击右下角按钮跳转并仔细阅读 <font color='darkgoldenrod'><b>Wiki</b></font> 相关页面中的说明"
    )
    pre_translation_replacement_page_table_row_01: str = "原文"
    pre_translation_replacement_page_table_row_02: str = "替换"
    pre_translation_replacement_page_table_row_03: str = "正则"

    # 译后替换
    post_translation_replacement_page_head_title: str = "译后替换"
    post_translation_replacement_page_head_content: str = "在翻译完成后，将译文中匹配的部分替换为指定的文本，执行的顺序为从上到下依次替换"
    post_translation_replacement_page_table_row_01: str = "原文"
    post_translation_replacement_page_table_row_02: str = "替换"
    post_translation_replacement_page_table_row_03: str = "正则"

    # 自定义提示词 - 中文
    custom_prompt_zh_page_head: str = "自定义中文提示词（不支持 SakuraLLM 模型）"
    custom_prompt_zh_page_head_desc: str = (
        "通过自定义提示词追加故事设定、行文风格等额外翻译要求"
        "<br>"
        "注意：前缀与后缀部分固定不可修改，只有 <font color='darkgoldenrod'><b>译文语言设置为中文时</b></font> 才会使用本页中的自定义提示词"
        ""
        ""
    )

    # 自定义提示词 - 英文
    custom_prompt_en_page_head: str = "自定义英文提示词（不支持 SakuraLLM 模型）"
    custom_prompt_en_page_head_desc: str = (
        "通过自定义提示词追加故事设定、行文风格等额外翻译要求"
        "<br>"
        "注意：前缀与后缀部分固定不可修改，只有 <font color='darkgoldenrod'><b>译文语言设置为非中文时</b></font> 才会使用本页中的自定义提示词"
        ""
        ""
    )

    # 翻译提示体系
    translation_prompt_mode_title: str = "基础提示模式"
    translation_prompt_mode_desc: str = "每次只使用一种基础模式；自定义模式仅替换基础提示词，固定工程协议仍会生效"
    translation_prompt_mode_common: str = "通用（COMMON）"
    translation_prompt_mode_cot: str = "逐步推理（COT）"
    translation_prompt_mode_think: str = "深度思考（THINK）"
    translation_prompt_mode_local: str = "本地模型（LOCAL）"
    translation_prompt_mode_custom: str = "自定义（CUSTOM）"
    translation_custom_prompt_zh_title: str = "中文基础提示词"
    translation_custom_prompt_zh_desc: str = "目标语言为中文时使用，完整替换所选基础提示模式"
    translation_custom_prompt_zh_placeholder: str = "输入中文基础提示词"
    translation_custom_prompt_en_title: str = "英文基础提示词"
    translation_custom_prompt_en_desc: str = "目标语言为非中文时使用，完整替换所选基础提示模式"
    translation_custom_prompt_en_placeholder: str = "输入英文基础提示词"
    translation_writing_style_title: str = "写作风格"
    translation_writing_style_desc: str = "独立追加到基础提示词，可与任意基础模式组合"
    translation_writing_style_none: str = "无（NONE）"
    translation_writing_style_literary: str = "文学化（LITERARY）"
    translation_writing_style_classical: str = "古典文风（CLASSICAL）"
    translation_writing_style_r18: str = "成人内容（R18）"
    translation_writing_style_custom: str = "自定义（CUSTOM）"
    translation_custom_writing_style_title: str = "自定义写作风格"
    translation_custom_writing_style_desc: str = "作为独立风格要求完整追加，不会替换基础提示词"
    translation_custom_writing_style_placeholder: str = "输入自定义写作风格要求"
    translation_prompt_preview_action: str = "查看当前提示词"
    translation_prompt_preview_tooltip: str = "查看当前配置实际使用的静态提示词内容"
    translation_prompt_preview_title: str = "当前提示词"
    translation_prompt_preview_base: str = "基础提示词"
    translation_prompt_preview_style: str = "写作风格"
    translation_prompt_preview_fixed: str = "固定协议"
    translation_prompt_preview_note: str = "仅显示当前配置的静态提示词，不包含运行时注入的世界观、角色卡、术语、禁翻项和待译文本。"
    translation_prompt_preview_empty: str = "当前分段没有内容"
    translation_prompt_preview_copy: str = "复制当前内容"
    translation_prompt_preview_load_failed: str = "读取当前提示词失败"
    translation_output_protocol_title: str = "翻译输出协议"
    translation_output_protocol_desc: str = "SINGLE_TEXT 只允许单条任务，选择后会自动启用单行翻译模式"
    translation_output_protocol_structured: str = "结构化 JSON（STRUCTURED）"
    translation_output_protocol_jsonline: str = "逐行 JSON（JSONLINE）"
    translation_output_protocol_single_text: str = "单条纯文本（SINGLE_TEXT）"
    translation_asset_regex_title: str = "项目资产正则匹配"
    translation_asset_regex_desc: str = "启用后，明确标记为正则的术语与禁翻项会按正则表达式匹配"
    translation_asset_token_budget_title: str = "项目资产 Token 预算"
    translation_asset_token_budget_desc: str = "每个任务可注入的动态项目资产 Token 上限"
    translation_asset_max_items_title: str = "项目资产条目上限"
    translation_asset_max_items_desc: str = "每个任务可注入的动态项目资产最大条目数"

    # 实验室
    laboratory_page_mtool_optimizer_enable: str = "MTool 优化器"
    laboratory_page_mtool_optimizer_enable_desc: str = (
        "在对 MTool 文本进行翻译时，至多可减少 40% 的 翻译时间 与 Token 消耗"
        "<br>"
        "可能导致 <font color='darkgoldenrod'><b>原文残留</b></font> 或 <font color='darkgoldenrod'><b>语句不连贯</b></font> 等问题，请 <font color='darkgoldenrod'><b>自行判断</b></font> 是否启用，并且只应在 <font color='darkgoldenrod'><b>翻译 MTool 文本时</b></font> 启用"
        ""
        ""
        ""
        ""
        ""
        ""
    )
    laboratory_page_auto_glossary_enable: str = "自动补全术语表（不支持 SakuraLLM 模型）"
    laboratory_page_auto_glossary_enable_desc: str = (
        "翻译的同时尝试自动补全术语表中缺失的专有名词条目，只有在 <font color='darkgoldenrod'><b>启用术语表功能</b></font> 时才生效"
        "<br>"
        "此功能设计目的仅为查漏补缺，并不能代替 <font color='darkgoldenrod'><b>KeywordGacha</b></font>，获取到的补充术语将直接 <font color='darkgoldenrod'><b>写入术语表</b></font>"
        "<br>"
        "可能会产生 <font color='darkgoldenrod'><b>不正确或不合适的术语条目</b></font>，请 <font color='darkgoldenrod'><b>自行判断</b></font> 是否启用，建议仅在 DeepSeek V3/R1 级别的强力模型使用此功能"
        ""
        ""
        ""
        ""
    )

    # 百宝箱
    tool_box_page_batch_correction: str = "批量修正"
    tool_box_page_batch_correction_desc: str = "根据翻译完成时生成的结果检查文件中的数据，对可能存在的翻译错误进行批量修正，实现快速修正译文结果的目的"
    tool_box_page_re_translation: str = "部分重翻"
    tool_box_page_re_translation_desc: str = "根据设置的筛选条件，重新对已完成的翻译文本中的部分内容进行翻译，主要用于内容的更新或错误的修正"
    tool_box_page_name_field_extraction: str = "姓名字段提取"
    tool_box_page_name_field_extraction_desc: str = (
        "提取 <font color='darkgoldenrod'><b>RenPy</b></font> 和 <font color='darkgoldenrod'><b>GalGame</b></font> 游戏文本中的角色姓名字段数据，"
        "自动生成对应的术语表数据，方便后续进行翻译"
    )

    # 百宝箱 - 批量修正
    batch_correction_page: str = "批量修正"
    batch_correction_page_desc: str = (
        "根据翻译完成时生成的结果检查文件中的数据，对可能存在的翻译错误进行批量修正，然后生成修正后的译文文件"
        "<br>"
        "工作流程："
        "<br>"
        "• 从 <font color='darkgoldenrod'><b>输入文件夹</b></font> 的翻译结果检查文件中提取可能需要修正的数据"
        "<br>"
        "• 检查提取出的数据，并根据实际情况对需要修正的条目进行修正"
        "<br>"
        "• 将修正后的数据注入 <font color='darkgoldenrod'><b>输入文件夹</b></font> 中的译文文件，然后在 <font color='darkgoldenrod'><b>输出文件夹</b></font> 生成修正后的译文文件"
    )
    batch_correction_page_step_01: str = "第一步 - 生成修正数据"
    batch_correction_page_step_01_desc: str = (
        "从结果检查文件中提取可能包含翻译错误的数据"
        "<br>"
        f"然后自动在 <font color='darkgoldenrod'><b>输出文件夹</b></font> 内生成用于编辑的数据文件 <font color='darkgoldenrod'><b>{path_result_batch_correction}</b></font>"
    )
    batch_correction_page_step_02: str = "第二步 - 注入修正数据"
    batch_correction_page_step_02_desc: str = (
        "检查数据文件中的内容，确认无误后 <font color='darkgoldenrod'><b>关闭</b></font> 文件，开始注入"
        "<br>"
        "请注意："
        "<br>"
        "• 除 <font color='darkgoldenrod'><b>修正列</b></font> 以外，不要修改数据文件内的其他数据"
        "<br>"
        "• 部分格式的译文文件名中会包含类似 <font color='darkgoldenrod'><b>.zh</b></font> 的语言后缀，在注入前请从文件名中移除语言后缀以正确匹配数据"
    )
    batch_correction_page_title_01: str = "文件名"
    batch_correction_page_title_02: str = "错误类型"
    batch_correction_page_title_03: str = "原文（勿修改此列）"
    batch_correction_page_title_04: str = "译文（勿修改此列）"
    batch_correction_page_title_05: str = "修正（请修改此列）"

    # 百宝箱 - 部分重翻
    re_translation_page: str = "部分重翻"
    re_translation_page_desc: str = (
        "将根据设置的筛选条件对 <font color='darkgoldenrod'><b>输入文件夹</b></font> 中的文本进行筛选，然后对符合条件的文本进行重翻"
        "<br>"
        "工作流程："
        "<br>"
        "• 分别从 <font color='darkgoldenrod'><b>输入文件夹</b></font> 的 <font color='darkgoldenrod'><b>src</b></font> 与 <font color='darkgoldenrod'><b>dst</b></font> 子目录中读取原文与译文"
        "<br>"
        "• 原文文件和译文文件的文件名和文件内容必须严格一一对应"
        "<br>"
        "• 根据本页中的设置筛选出需要重翻的文本，按正常流程进行翻译，翻译完成后输出更新后的译文文件"
    )
    re_translation_page_white_list: str = "关键字 - 白名单"
    re_translation_page_white_list_desc: str = (
        "包含这些关键字的文本将被重新翻译，可以填入多个关键字，每行一个，只需要命中其中之一即判断为需要重翻的文本"
        ""
        ""
    )
    re_translation_page_alert_not_equal: str = "原文与译文的行数不匹配 …"

    # 百宝箱 - 姓名字段提取
    name_field_extraction_page: str = "姓名字段提取"
    name_field_extraction_page_desc: str = (
        "将从 <font color='darkgoldenrod'><b>输入文件夹</b></font> 中所有符合条件的文件中提取角色姓名字段，自动生成对应的术语表数据"
        "<br>"
        "请注意：此功能 <font color='darkgoldenrod'><b>不能提取正文内的术语</b></font>，不能代替 <font color='darkgoldenrod'><b>KeywordGacha</b></font> 工具"
        "<br>"
        "支持格式："
        "<br>"
        "• RenPy 导出游戏文本（.rpy）"
        "<br>"
        "• VNTextPatch 或 SExtractor 导出带 name 字段的游戏文本（.json）"
    )
    name_field_extraction_page_step_01: str = "第一步 - 提取数据"
    name_field_extraction_page_step_01_desc: str = (
        "提取姓名字段及与其相关的上下文，发送至翻译器进行翻译"
        "<br>"
        f"翻译完成后，将在 <font color='darkgoldenrod'><b>输出文件夹</b></font> 内生成 <font color='darkgoldenrod'><b>{path_result_name_field_extraction}</b></font> 文件"
    )
    name_field_extraction_page_step_02: str = "第二步 - 生成术语表"
    name_field_extraction_page_step_02_desc: str = (
        f"将从 <font color='darkgoldenrod'><b>输出文件夹</b></font> 内的 <font color='darkgoldenrod'><b>{path_result_name_field_extraction}</b></font> 文件中提取翻译后的数据"
        "<br>"
        "然后生成对应的术语表数据，请注意检查生成的术语表数据是否正确"
    )

    # 工具箱与工作台界面
    add_language_select_project_s_game_folder: str = '选择项目的 game 目录'
    add_language_adds_language_menu_so_players_can_switch: str = (
        "此功能将在游戏中添加语言切换菜单，允许玩家在游戏设置中切换语言。\n\n操作步骤：\n1. 选择项目的 game 目录\n2. 点击'添加语言入口'按钮\n3. 脚本将自动注入语言切换代"
        '码到游戏中\n\n注意：此操作会修改游戏脚本，建议先备份'
    )
    add_language_add_language_menu: str = '添加语言入口'
    add_language_select_game_folder: str = '选择 game 目录'
    add_language_add_language_menu_2: str = '🌐 添加语言入口'
    add_language_project_settings: str = '📁 项目配置'
    add_language_game_folder: str = 'game 目录:'
    add_language_about_tool: str = 'ℹ️ 功能说明'
    add_language_language_menu_script_added_hook_add_change: str = '已添加语言入口脚本 (hook_add_change_language_entrance.rpy)'
    add_language_select_game_folder_2: str = '请选择 game 目录'
    add_language_folder_does_not_exist: str = '目录不存在'
    add_language_hook_file_missing: str = '缺少 hook 文件: {hook_source}'
    add_language_failed_add_language_menu: str = '添加语言入口失败: {e}'
    android_build_android_shell_projects_download_modified_sdk_qq: str = '如果制作安卓壳子，请在群：821152470 下载魔改 SDK。'
    android_build_select_renpy_sdk_folder: str = '选择 renpy-sdk 目录'
    android_build_select_ren_py_project_root_folder: str = "选择 Ren'Py 项目根目录"
    android_build_display_name: str = '显示名称'
    android_build_e_g_com_example_game: str = '例如 com.example.game'
    android_build_e_g_1_0_0: str = '例如 1.0.0'
    android_build_automatically_update_java_code: str = '自动更新 Java 代码'
    android_build_automatically_update_icons: str = '自动更新图标'
    android_build_icons_place_android_icon_foreground_png_android: str = (
        '图标替换：项目根目录放 android-icon_foreground.png 与 android-icon_background.png（PNG，建议 1024x1024）。'
        '\n启动图：android-presplash.png/jpg、android-downloading.png/jpg（建议 930x580 或保持同比例）。'
    )
    android_build_signing_name: str = '签名名称:'
    android_build_organization_name_used_generate_keystore_optional: str = '生成 keystore 时的组织/名称 (可选)'
    android_build_write_android_json: str = '写入 android.json'
    android_build_check_environment: str = '检查环境'
    android_build_install_sdk: str = '安装 SDK'
    android_build_generate_signing_key: str = '生成签名'
    android_build_generates_apk_only_opens_rapt_bin_when: str = '仅生成 APK。构建完成后自动打开 rapt/bin。'
    android_build_start_build: str = '开始构建'
    android_build_open_rapt_bin: str = '打开 rapt/bin'
    android_build_separate_multiple_folders_semicolons_new_lines_leave: str = '多个目录用分号或换行分隔，留空默认使用 game'
    android_build_add: str = '添加'
    android_build_detect: str = '检测'
    android_build_back_up_package_folders_zip_file_project: str = '备份打包目录并压缩为 zip（保存到项目根目录）'
    android_build_separate_folders_commas_semicolons_leave_blank_delete: str = '多个目录用逗号/分号分隔，留空不删除（默认: {default_dirs}）'
    android_build_separate_folders_commas_semicolons_leave_blank_delete_2: str = '多个目录用逗号/分号分隔，留空不删除'
    android_build_generate_archive_rpa_clean_resources: str = '生成 archive.rpa + 清理资源'
    android_build_select_ren_py_sdk_folder: str = "选择 Ren'Py SDK 目录"
    android_build_select_ren_py_project_folder: str = "选择 Ren'Py 项目目录"
    android_build_select_package_folder: str = '选择打包目录'
    android_build_done: str = '完成'
    android_build_detected_folder_s_replaced_current_list: str = '已检测到 {detected_count} 个目录，已覆盖'
    android_build_android_json_updated: str = 'android.json 已更新'
    android_build_checking_environment: str = '检查环境中...'
    android_build_installing_sdk: str = '安装 SDK 中...'
    android_build_generating_signing_key: str = '生成签名中...'
    android_build_building: str = '构建中...'
    android_build_processing_shell_package: str = '壳子处理中...'
    android_build_shell_package_completed: str = '壳子制作完成'
    android_build_archive_rpa_created: str = 'archive.rpa 打包完成'
    android_build_android_build: str = '安卓打包'
    android_build_paths: str = '路径设置'
    android_build_project_folder: str = '项目目录:'
    android_build_android_configuration_android_json: str = 'Android 配置 (android.json)'
    android_build_app_name: str = '应用名:'
    android_build_package_name: str = '包名:'
    android_build_version: str = '版本:'
    android_build_environment_signing: str = '环境与签名'
    android_build_build: str = '构建'
    android_build_shell_package: str = '壳子制作'
    android_build_pack_selected_folders_archive_rpa_project_root: str = '将指定目录打包为 archive.rpa（保存到项目根目录），并清理大体积资源目录。'
    android_build_package_folders: str = '打包目录:'
    android_build_cleanup_folders: str = '清理目录:'
    android_build_select_ren_py_sdk_folder_first: str = "请先选择 Ren'Py SDK 目录"
    android_build_select_project_folder_first: str = '请先选择项目目录'
    android_build_project_folder_does_not_exist: str = '项目目录不存在: {project_dir}'
    android_build_game_folder_not_found: str = '未找到 game 目录: {game_dir}'
    android_build_no_resource_folders_detected_field_cleared: str = '未检测到资源目录，已清空'
    android_build_enter_app_name_package_name_version: str = '请填写应用名、包名和版本'
    android_build_no_signing_key_found_generate_one_first: str = '未检测到签名文件，请先生成签名'
    android_build_build_completed: str = '构建完成'
    android_build_no_files_found_package: str = '未找到可打包的文件'
    android_build_rapt_bin_not_found_run_build_first: str = '未找到 rapt/bin，请先构建'
    android_build_task_already_running: str = '任务正在进行中'
    android_build_failed: str = '失败'
    android_build_failed_create_distribution_folder: str = '分发目录生成失败'
    android_build_build_failed: str = '构建失败'
    android_build_confirm_shell_processing: str = '确认壳子处理'
    android_build_build_archive_rpa_project_root_clean_configured: str = (
        '将打包 archive.rpa（保存到项目根目录），并清理配置的资源目录。\n此操作会修改工程文件，建议先备份。'
    )
    android_build_package_folder_does_not_exist: str = '打包目录不存在: {source_dir}'
    android_build_package_path_not_folder: str = '打包目录不是文件夹: {source_dir}'
    android_build_task_completed: str = '任务完成'
    android_build_task_failed: str = '任务失败'
    android_build_backup_failed: str = '备份失败: {exc}'
    direct_rpy_translate_tl_rpy_files_engine_workflow: str = '📄 直接翻译 tl/.rpy（Engine 流程）'
    direct_rpy_select_game_exe_project_folder: str = '选择游戏 exe 或项目目录'
    direct_rpy_optional_defaults_game_tl_language: str = '可选，默认尝试 game/tl/<语言>'
    direct_rpy_create_bak_backup_before_writing: str = '写入前自动备份 .bak'
    direct_rpy_start_translation: str = '开始翻译'
    direct_rpy_select_game_exe_folder: str = '选择游戏 exe 或目录'
    direct_rpy_executable_exe_all_files: str = '可执行文件 (*.exe);;所有文件 (*)'
    direct_rpy_select_tl_folder: str = '选择 tl 目录'
    direct_rpy_requesting_stop: str = '正在请求停止...'
    direct_rpy_translating: str = '翻译中... {current}/{total}'
    direct_rpy_translation_complete: str = '翻译完成'
    direct_rpy_engine_translation_complete: str = 'Engine 翻译完成'
    direct_rpy_stopped: str = '已停止'
    direct_rpy_path_settings: str = '📁 路径设置'
    direct_rpy_game_file_folder: str = '游戏文件或目录:'
    direct_rpy_tl_folder: str = 'tl 目录:'
    direct_rpy_tl_language_folder_name: str = 'tl 语言目录名:'
    direct_rpy_target_language: str = '目标语言:'
    direct_rpy_simplified_chinese: str = '简体中文'
    direct_rpy_traditional_chinese: str = '繁体中文'
    direct_rpy_english: str = '英语'
    direct_rpy_japanese: str = '日语'
    direct_rpy_korean: str = '韩语'
    direct_rpy_translation_has_been_sent_engine_please_wait: str = '已委托 Engine 翻译，请稍候...'
    direct_rpy_started: str = '已开始'
    direct_rpy_unified_engine_workflow_has_started_progress_appears: str = '已切换到统一 Engine 流程，进度见下方。'
    direct_rpy_could_not_resolve_ren_py_project_paths: str = "无法解析 Ren'Py 项目路径"
    direct_rpy_tl_folder_does_not_exist: str = 'tl 目录不存在: {tl_dir}'
    direct_rpy_tl_folder_does_not_exist_2: str = 'tl/{tl_name} 目录不存在: {input_tl_dir}'
    direct_rpy_select_game_file_tl_folder_first: str = '请先选择游戏文件或 tl 目录'
    direct_rpy_tl_folder_not_found_run_extraction_select: str = '未找到 tl/{tl_name} 目录，请先执行抽取或指定 tl 目录'
    extract_json_text_extraction_json: str = '文本提取 JSON'
    extract_json_complete_json_workflow_extract_export_json_translate: str = '完整的 JSON 翻译工作流：提取 → 导出 JSON → 人工翻译 → 导入 → 应用到 tl'
    extract_json_select_game_executable_exe: str = '选择游戏可执行文件 (.exe)'
    extract_json_preview_file_count: str = '预览文件数'
    extract_json_extract_export_json: str = '提取并导出 JSON'
    extract_json_exported_json_stores_all_rpy_text_one: str = '说明：导出的 JSON 会将所有 .rpy 文本写入单个文件，按文件路径分组条目'
    extract_json_json_import_export: str = 'JSON 导入/导出'
    extract_json_import_json_apply_tl: str = '从 JSON 导入并应用到 tl'
    extract_json_translate_exported_json_then_import_tl_folder: str = '说明：导出后在 JSON 中完成翻译，然后导入并应用到 tl 目录。结构为 {"translations": {file: [...]}}。'
    extract_json_clean_tl_duplicates_empty_lines: str = '清理 tl 重复与空行'
    extract_json_export_tl_json: str = '提取 tl→JSON'
    extract_json_select_ren_py_game_executable: str = "选择 Ren'Py 游戏可执行文件"
    extract_json_executable_files_exe: str = '可执行文件 (*.exe)'
    extract_json_counting_files_text_entries: str = '正在统计文件和文本数量...'
    extract_json_export_json_file: str = '导出 JSON 文件'
    extract_json_json_files_json: str = 'JSON 文件 (*.json)'
    extract_json_extracting_text_generating_json: str = '正在提取文本并生成 JSON...'
    extract_json_select_json_file: str = '选择 JSON 文件'
    extract_json_game_file: str = '游戏文件:'
    extract_json_tl_language: str = 'tl 语言:'
    extract_json_select_game_file: str = '请选择游戏文件'
    extract_json_game_file_does_not_exist: str = '游戏文件不存在'
    extract_json_preview_results: str = '预览结果'
    extract_json_found_text_entries_files_tl_all_entries: str = (
        '发现 {total_files} 个文件，共 {total_entries} 条文本 (tl/{tl_name})\n所有条目将写入单个 JSON，使用文件名作为键区分来源'
    )
    extract_json_game_directory_not_found_select_correct_project: str = '未找到 game/ 目录，请选择正确的项目'
    extract_json_importing_translations_json: str = '正在从 JSON 导入并应用翻译...'
    extract_json_tl_cleanup_complete: str = 'tl 清理完成'
    extract_json_select_export_path: str = '选择导出路径'
    extract_json_failed_count_entries: str = '统计失败: {e}'
    extract_json_success: str = '成功'
    extract_json_json_export_completed_tl_all_entries_written: str = (
        'JSON 导出成功 (tl/{tl_name})\n所有条目写入同一个文件，按文件名分组'
    )
    extract_json_no_text_extracted_export_skipped: str = '未提取到任何文本或导出被跳过'
    extract_json_export_failed: str = '导出失败: {e}'
    extract_json_no_usable_translation_entries_found_json_file: str = 'JSON 中未找到可用的翻译条目'
    extract_json_applied_tl_processed_translations_files: str = (
        '已应用到 tl/{target_lang}\n处理了 {total_files} 个文件，{total_entries} 条翻译'
    )
    extract_json_failed_apply_translations: str = '应用翻译失败'
    extract_json_import_failed: str = '导入失败: {e}'
    extract_json_tl_folder_not_found: str = '未找到 tl 目录: {tl_dir}'
    extract_json_tl_cleanup_failed: str = 'TL 清理失败: {e}'
    extract_json_tl_export_completed_translations_files_written_one: str = (
        'TL 导出成功\n{total_files} 个文件，{total_entries} 条翻译，均写入同一个 JSON\n跳过 {skipped} 条资源/占位符'
    )
    extract_json_tl_export_failed: str = 'TL 导出失败'
    extract_json_tl_export_failed_2: str = 'TL 导出失败: {e}'
    font_replace_if_game_cannot_display_translated_text_font: str = (
        '💡 说明：游戏无法显示中文通常是因为字体不支持。\n本功能默认会注入一套预置字体包到 tl 目录（不改原文件）。\n只需选择游戏目录，点击「一键注入字体」即可。'
    )
    font_replace_select_project_root_game_folder: str = '选择游戏目录（项目根或 game 目录）'
    font_replace_select_game_folder_first: str = '请先选择游戏目录'
    font_replace_auto_detect: str = '自动检测'
    font_replace_select_translation_language_receive_font_pack_chinese: str = '选择要注入字体包的翻译语言。如果是汉化，通常选择 chinese。'
    font_replace_inject_fonts: str = '✨ 一键注入字体'
    font_replace_expand: str = '展开'
    font_replace_leave_blank_use_bundled_font: str = '留空则使用内置中文字体'
    font_replace_not_scanned: str = '尚未扫描'
    font_replace_only_fonts_referenced_scripts_listed_here_unreferenced: str = '这里只显示脚本中实际引用到的字体；game/fonts 中存在但未被引用的字体会单独统计。'
    font_replace_replace_all_detected_fonts: str = '替换所有检测到的字体'
    font_replace_leave_blank_replace_all_detected_fonts: str = '留空则替换所有检测到的字体'
    font_replace_also_generate_gui_font_hook_optional: str = '同时生成 GUI 字体 Hook（可选）'
    font_replace_creates_font_hook_tl_lang_gui_rpy: str = '会在 tl/<lang>/gui.rpy 生成字体 Hook（兼容旧项目）'
    font_replace_automatically_back_up_before_replacing_recommended: str = '替换前自动备份（推荐）'
    font_replace_scan_all_fonts: str = '检测所有字体'
    font_replace_replace_all_fonts: str = '替换所有字体'
    font_replace_select_game_folder: str = '选择 game 目录'
    font_replace_select_font_file: str = '选择字体文件'
    font_replace_font_files_ttf_otf_all_files: str = '字体文件 (*.ttf *.otf);;所有文件 (*)'
    font_replace_game_folder_rescanned: str = '已重新扫描游戏目录'
    font_replace_font_injection: str = '🔤 字体注入'
    font_replace_select_game_folder_2: str = '📁 选择游戏目录'
    font_replace_advanced_options: str = '⚙️ 高级选项'
    font_replace_custom_font: str = '自定义字体:'
    font_replace_detected_font_references: str = '检测到的字体引用:'
    font_replace_original_font: str = '指定原字体:'
    font_replace_collapse: str = '收起'
    font_replace_default_language_global_replacement: str = '默认语言 (全局替换)'
    font_replace_scan_complete_font_reference_s_font_file: str = '✅ 扫描完成：检测到 {font_count} 个字体引用，发现 {font_file_count} 个字体文件，{lang_count} 个翻译语言'
    font_replace_scripts_reference_font_s_font_file_s: str = (
        '脚本中引用了 {font_count} 个字体；game/fonts、game/gui 等目录中共发现 {font_file_count} 个字体文件。“替换所有检测到的字体”'
        '只会替换脚本中实际引用到的字体。'
    )
    font_replace_replacing_fonts_please_wait: str = '正在替换字体，请稍候...'
    font_replace_font_replacement_complete_file_s_replacement_s: str = '字体替换完成：修改 {replaced_files} 个文件，共 {replaced_count} 处'
    font_replace_backup_fonts_backup: str = (
        '\n已备份到: fonts_backup/{details_backup_name}'
    )
    font_replace_font_replacement_failed: str = '字体替换失败：{message}'
    font_replace_font_replacement_failed_2: str = '替换失败: {message}'
    font_replace_folder_does_not_exist: str = '❌ 目录不存在'
    font_replace_scan_failed: str = '❌ 扫描失败: {e}'
    font_replace_folder_does_not_exist_2: str = '目录不存在'
    font_replace_font_injection_failed: str = '注入失败: {message}'
    font_replace_font_injection_failed_2: str = '注入失败: {e}'
    font_replace_font_replacement_failed_3: str = '替换失败: {e}'
    font_replace_no_font_references_detected_font_file_s: str = '未检测到字体引用（已发现 {discovered_font_files_count} 个字体文件）'
    font_replace_no_font_references_detected: str = '未检测到字体引用'
    font_replace_font_pack_injected_but_gui_hook_could: str = '字体包已注入，但 GUI Hook 生成失败'
    font_replace_custom_font_file_does_not_exist: str = '自定义字体文件不存在'
    font_replace_bundled_font_not_found: str = '未找到内置字体'
    font_replace_select_replace_all_detected_fonts_enter_original: str = '请勾选“替换所有检测到的字体”或填写要替换的原字体'
    font_replace_no_font_references_detected_2: str = '未检测到任何字体引用'
    local_glossary_added_candidates_updated_existing_entries_scanned_text: str = '已合并 {added_count} 条新候选，补全 {updated_count} 条现有条目，候选文本 {corpus_count} 条。'
    local_glossary_category: str = '类别'
    local_glossary_notes: str = '备注'
    local_glossary_hits: str = '命中数'
    local_glossary_project_glossary: str = '📚 本地词库管理'
    local_glossary_import_glossary_entries_excel_confirm_save_them: str = '支持从 Excel 导入术语表，确认后保存到当前项目资产，并可导出为 Excel 共享给团队。'
    local_glossary_project_data: str = '配置与同步'
    local_glossary_import_excel: str = '导入 Excel'
    local_glossary_export_excel: str = '导出 Excel'
    local_glossary_save_project: str = '保存到项目'
    local_glossary_load_project: str = '从项目加载'
    local_glossary_count_hits: str = '统计命中'
    local_glossary_count_how_many_cached_output_entries_contain: str = '基于当前 output/cache 中的缓存条目统计每条术语命中的文本数量'
    local_glossary_table_actions: str = '表格维护'
    local_glossary_deduplicate: str = '去重重复'
    local_glossary_deduplicate_source_text_while_preserving_existing_translations: str = '按原文去重，优先保留已有译文/类别/备注'
    local_glossary_add_entry: str = '新增条目'
    local_glossary_confirm_selected: str = '确认选中候选'
    local_glossary_mark_selected_candidates_confirmed_only_confirmed_candidates: str = '将选中的候选标记为已确认；保存时仅已确认且有译文的候选会转为正式术语'
    local_glossary_delete_selected: str = '删除选中'
    local_glossary_clear_all: str = '清空全部'
    local_glossary_delete_all_glossary_entries_loaded_candidates_current: str = '删除当前项目中的所有正式术语和已载入候选'
    local_glossary_auto_categorize: str = '自动分类'
    local_glossary_use_ner_first_when_available_then_fill: str = '先尝试 NER（需模型），再用关键词规则填充空白类别'
    local_glossary_scan_translate: str = '扫描与翻译'
    local_glossary_scan_term_candidates: str = '扫描术语候选'
    local_glossary_scan_game_scripts_proper_noun_candidates_configured: str = '扫描游戏源码中的专有名词候选；配置了 LLM 时会进一步提升召回率'
    local_glossary_stop_scan: str = '停止扫描'
    local_glossary_request_current_candidate_scan_stop_after_any: str = '请求停止当前术语候选扫描；若正在等待某个 LLM 分块响应，将在该分块结束后停止'
    local_glossary_scan_character_names: str = '扫描角色名'
    local_glossary_scan_game_folder_character_names_replace_previous: str = '扫描游戏目录，自动提取角色名到术语表（清空旧的自动提取数据）'
    local_glossary_translate_llm: str = 'LLM 批量翻译'
    local_glossary_use_configured_llm_api_fill_blank_placeholder: str = '使用已配置的翻译引擎（LLM/API）批量翻译空译文/占位译文，不会覆盖已有译文'
    local_glossary_fast_translation: str = '极速批量翻译'
    local_glossary_use_google_bing_faster_batch_translation_without: str = '使用 Google/Bing 进行批量翻译（更快），不覆盖已有译文'
    local_glossary_candidate_scan_has_not_started: str = '术语候选扫描未开始'
    local_glossary_glossary_entries_cells_editable: str = '术语表（可直接编辑单元格）'
    local_glossary_confirmed: str = '已确认'
    local_glossary_confirmed_candidates_add_translations_then_save_them: str = '已标记 {confirmed} 条候选；补全译文后点击“保存到项目”即可转为正式术语'
    local_glossary_cleared: str = '已清空'
    local_glossary_deleted_all_glossary_entries_loaded_candidates_current: str = '已删除当前项目中的正式术语和已载入候选'
    local_glossary_translation_started: str = '开始翻译'
    local_glossary_translating_glossary_entries_llm: str = '正在使用 LLM 翻译 {tasks_count} 条术语…'
    local_glossary_translating_glossary_entries: str = '正在翻译 {tasks_count} 条术语…'
    local_glossary_preparing_term_candidate_scan: str = '正在准备术语候选扫描…'
    local_glossary_scan_started: str = '开始扫描'
    local_glossary_scanning_game_scripts_term_candidates: str = '正在扫描游戏源码中的术语候选…'
    local_glossary_stopping_term_candidate_scan: str = '正在请求停止术语候选扫描…'
    local_glossary_scan_stop_after_current_batch_finishes: str = '已请求停止术语候选扫描，当前分块结束后会停止'
    local_glossary_term_candidate_scan_stopped: str = '术语候选扫描已停止'
    local_glossary_successful_llm_batches: str = ' LLM 分块成功 {llm_chunks_success}/{max_llm_chunks_total_llm_chunks_success}。'
    local_glossary_term_candidate_scan_completed: str = '术语候选扫描完成'
    local_glossary_statistics_completed: str = '统计完成'
    local_glossary_analyzed_glossary_entries_across_cached_entries: str = '已统计 {counts_count} 条术语，样本条目 {counted_item_total} 条'
    local_glossary_completed: str = '完成'
    local_glossary_loaded_glossary_entries_current_project_candidates_need: str = '已从当前项目加载 {converted_count} 条术语，其中 {candidate_count} 条待确认'
    local_glossary_saved: str = '保存成功'
    local_glossary_saved_confirmed_glossary_entries_kept_incomplete_candidates: str = '已确认 {formal_count} 条正式术语，保留 {candidate_count} 条待补全候选'
    local_glossary_select_glossary_excel_file: str = '选择术语 Excel 文件'
    local_glossary_excel_files_xlsx: str = 'Excel 文件 (*.xlsx)'
    local_glossary_save_glossary_excel_file: str = '保存术语 Excel'
    local_glossary_found_character_names_confirmation_removed_previous_auto: str = '已扫描到 {new_entries_count} 个待确认角色名，已清除旧的自动提取候选'
    local_glossary_translating_glossary: str = '正在翻译术语库...'
    local_glossary_glossary_translation_completed: str = '术语库翻译完成'
    local_glossary_translated_entries: str = '已翻译 {results_count} 条术语'
    local_glossary_batch_entries: str = '第 {batch_index}/{total_batches} 批，{srcs_count} 条'
    local_glossary_translated_entries_2: str = '已翻译 {all_results_count} 条术语'
    local_glossary_select_entry_delete: str = '请选择需要删除的条目'
    local_glossary_select_one_more_candidates_confirm: str = '请选择需要确认的候选条目'
    local_glossary_selected_entries_not_pending_candidates_already_confirmed: str = '选中条目不是待确认候选，或已经确认'
    local_glossary_table_empty: str = '表格为空，暂无可去重的数据'
    local_glossary_removed_duplicate_entries_kept: str = '已去除重复 {removed} 条，保留 {deduped_count} 条'
    local_glossary_no_duplicate_entries_found: str = '未发现重复条目'
    local_glossary_glossary_translation_already_running: str = '术语库翻译正在进行中，请稍候…'
    local_glossary_there_no_entries_translate_translation_column_already: str = '没有需要翻译的条目（译文列已填充）'
    local_glossary_no_translation_engine_available_configure_enable_platform: str = '未找到可用的翻译引擎，请先在“翻译引擎”里配置并启用一个平台。'
    local_glossary_translation_failed: str = '翻译失败'
    local_glossary_translation_completed: str = '翻译完成'
    local_glossary_filled_translations_confirm_candidates_save_them_project: str = '已填充 {applied} 条译文（别忘了点击“确认并保存到项目”）'
    local_glossary_translation_finished_without_usable_results_service_may: str = '翻译已结束，但没有产生可用译文（可能接口返回原文）'
    local_glossary_select_game_folder_containing_game_subfolder: str = '选择游戏目录（包含 game 子目录）'
    local_glossary_game_folder_does_not_exist: str = '游戏目录不存在: {target_path}'
    local_glossary_term_candidate_scan_already_running: str = '术语候选扫描正在进行中，请稍候…'
    local_glossary_no_compatible_llm_available_scan_use_rules: str = '未找到可用 LLM，将仅使用规则候选扫描。'
    local_glossary_no_term_candidate_scan_running: str = '当前没有正在运行的术语候选扫描'
    local_glossary_term_candidate_scan_failed: str = '术语候选扫描失败'
    local_glossary_scan_failed: str = '扫描失败'
    local_glossary_scan_result_has_invalid_format: str = '扫描结果格式无效'
    local_glossary_scan_completed_without_usable_term_candidates: str = '术语候选扫描完成，但没有生成可用条目'
    local_glossary_scan_completed: str = '扫描完成'
    local_glossary_hit_statistics_already_running: str = '命中统计正在进行中，请稍候…'
    local_glossary_there_no_glossary_entries_analyze: str = '当前术语表为空，暂无可统计的数据'
    local_glossary_statistics_failed: str = '统计失败'
    local_glossary_statistics_result_has_invalid_format: str = '统计结果格式无效'
    local_glossary_statistics_result_does_not_contain_hit_counts: str = '统计结果缺少命中数'
    local_glossary_glossary_changed_run_statistics_again: str = '术语表内容已变化，请重新执行一次统计'
    local_glossary_openpyxl_not_installed_so_excel_files_cannot: str = '未安装 openpyxl，无法导入 Excel'
    local_glossary_imported: str = '导入成功'
    local_glossary_imported_glossary_entries: str = '已导入 {items_count} 条术语'
    local_glossary_openpyxl_not_installed_so_excel_files_cannot_2: str = '未安装 openpyxl，无法导出 Excel'
    local_glossary_table_empty_no_file_exported: str = '当前表格为空，未导出文件'
    local_glossary_exported: str = '导出成功'
    local_glossary_saved_2: str = '已保存到 {path}'
    local_glossary_game_folder_does_not_exist_2: str = '游戏目录不存在: {game_path}'
    local_glossary_no_character_names_found_check_selected_game: str = '未找到角色名，请确认游戏目录正确'
    local_glossary_ner_categorized_entries_keyword_rules_categorized: str = 'NER 填充 {ner_count} 条，关键词填充 {kw_count} 条'
    local_glossary_no_entries_could_categorized_check_model_source: str = '未找到可填充的类别（可检查模型或文本内容）'
    local_glossary_no_entries_translate: str = '没有需要翻译的条目'
    local_glossary_no_translation_engine_selected_configure_enable_platform: str = '未选择翻译引擎，请先在“翻译引擎”里设置并启用一个平台。'
    local_glossary_translating_glossary_llm: str = '正在使用 LLM 翻译术语库… ({batch_label})'
    local_glossary_waiting_model: str = '正在等待模型返回… ({batch_label})'
    local_glossary_translated_glossary_entries: str = '已完成术语翻译 {len_batch_total}/{total}'
    local_glossary_game_folder_set: str = '已设置游戏目录为: {source_root}'
    local_glossary_select_game_folder_first: str = '请先选择游戏目录'
    local_glossary_active_platform_does_not_support_term_extraction: str = '当前平台不支持术语抽取，将仅使用规则候选扫描。'
    local_glossary_scan_completed_but_candidates_could_not_saved: str = '术语候选扫描完成，但保存项目候选失败'
    local_glossary_save_failed: str = '保存失败'
    local_glossary_candidates_displayed_but_could_not_saved_project: str = '候选已显示但未能写入项目缓存：{exc}'
    local_glossary_source_translation_column_not_found_check_template: str = '未找到“原文/译文”列，请确认模板。'
    local_glossary_categorized_entries: str = '已为 {changed} 条填充类别'
    local_glossary_no_blank_categories_could_matched: str = '没有需要填充的类别或未找到匹配'
    local_glossary_no_ner_model_found_under_resource_models: str = '未找到 NER 模型（Resource/Models/ner/*），已跳过'
    local_glossary_ner_categorized_entries: str = 'NER 填充了 {changed} 条类别'
    local_glossary_no_entries_could_categorized: str = '未找到可填充的类别'
    local_glossary_spacy_not_installed: str = '未安装 spaCy：{e}'
    local_glossary_failed_load_ner_model: str = '加载 NER 模型失败: {e}'
    onekey_cleaning_incremental_folders: str = '正在清理增量目录...'
    onekey_restoring_translation_paths: str = '正在恢复翻译路径配置...'
    onekey_applied_translation_files_game_folder_you_can: str = (
        '已成功应用 {success_count} 个翻译文件到游戏目录！\n现在可以启动游戏查看翻译效果。'
    )
    onekey_step_5: str = '步骤 {step}/5：{title}'
    onekey_select_game: str = '选择游戏'
    onekey_quick_start: str = '💡 小白指南'
    onekey_1_select_game_folder_contains_game_subfolder: str = (
        '1. 选择游戏目录（包含 game 文件夹的那个）\n2. 点击「开始提取文本」自动抽取翻译\n3. 完成后点击「开始翻译」即可\n💬 如果之前翻译过，会自动保留已有翻译'
    )
    onekey_enter_paste_game_folder_path_example_d: str = '输入或粘贴游戏目录路径，例如: D:\\Games\\MyGame'
    onekey_browse: str = '浏览...'
    onekey_existing_translation_detected: str = '🔍 检测到已有翻译'
    onekey_game_already_has_translation_files_choose_how: str = '该游戏已有翻译文件，请选择处理方式：'
    onekey_incremental_extraction_recommended: str = '增量抽取（推荐）'
    onekey_keep_existing_translations_extract_new_untranslated_entries: str = '保留已有翻译，抽取新增内容 + 未翻译占位'
    onekey_full_extraction_start_over: str = '完整抽取（重做全量）'
    onekey_backs_up_regenerates_tl_lang_existing_placeholders: str = '会把 tl/<lang> 备份后重新生成，占位会被重置，慎用'
    onekey_back_up_old_translation_extract_everything_again: str = '备份旧翻译后重新抽取全部内容，仅在需要推倒重做时使用'
    onekey_tip_incremental_extraction_protects_existing_translations_use: str = '小提示：默认选择增量抽取，避免覆盖已有翻译；完整抽取只在重做全量时使用。'
    onekey_merge_automatically_remove_duplicates_after_extraction: str = '抽取后自动合并并清理重复'
    onekey_advanced_options: str = '高级选项'
    onekey_inject_ui_translation_pack_base_box: str = '注入 UI 翻译包（base_box）'
    onekey_injects_bundled_ui_translations_start_save_settings: str = (
        '自动注入预置的 UI 翻译（开始、保存、设置等）。\n如果你已有自定义 UI 翻译，请取消勾选。'
    )
    onekey_extract_translate_hidden_built_text_creates_renpybox: str = '提取游戏内置隐藏文本并翻译（生成 renpybox_bytecode_strings.rpy）'
    onekey_some_player_visible_text_embedded_compiled_files: str = (
        "游戏中部分玩家可见文本写死在程序文件里，Ren'Py 官方抽取识别不到。\n勾选后会自动找出这些隐藏文本，作为普通翻译条目一并翻译（写入 tl/<语言>/renpybox_byt"
        'ecode_strings.rpy）。\n不勾选则这些文本不纳入标准翻译，翻译时容易漏掉，需要之后靠补全功能兜底。'
    )
    onekey_review_untranslated_uppercase_abbreviations_uses_additional_quota: str = '对未翻译的大写缩写做二次确认（会额外消耗额度）'
    onekey_clear_skipped_candidates: str = '清除判定不译清单'
    onekey_click_extract_text_begin_existing_translations_preserved: str = '直接点击“开始提取文本”即可，完成后进入翻译。如果已有翻译，默认会保留。'
    onekey_skip_extraction_translate: str = '跳过抽取，直接翻译 →'
    onekey_extract_text: str = '开始提取文本 →'
    onekey_extract_text_2: str = '提取文本'
    onekey_ready_extract: str = '准备开始提取...'
    onekey_text_extracted_game_translation_files_when_finishes: str = '正在从游戏中提取文本并生成翻译文件，请稍候。完成后点击“开始翻译”进入下一步，随时可重新抽取。'
    onekey_extract_again: str = '重新抽取'
    onekey_project_changed_extract_again: str = '项目已切换，请重新提取'
    onekey_open_rpa_unpacker: str = '前往 RPA 解包'
    onekey_skip_step: str = '跳过此步骤'
    onekey_next: str = '下一步 →'
    onekey_merge_remove_duplicates: str = '合并并清理重复'
    onekey_clear_skipped_candidates_2: str = '清除判定不译清单'
    onekey_these_terms_translated_again_during_next_run: str = '清除后这些词会在下次翻译时重新尝试翻译。'
    onekey_clear: str = '确认清除'
    onekey_terms_translation_context: str = '术语与翻译上下文'
    onekey_looking_glossary_files_project: str = '正在查找项目中的术语表...'
    onekey_open_local_glossary: str = '📂 打开本地词库管理'
    onekey_use_scan_term_candidates_local_glossary_find: str = '可在本地词库页手动执行“扫描术语候选”，补齐角色名之外的正文专名'
    onekey_open_do_not_translate_list: str = '🚫 打开禁翻表管理'
    onekey_extract_character_names: str = '🔍 自动提取角色名'
    onekey_open_character_world_workbench: str = '🎭 打开角色/世界观工作台'
    onekey_manage_worldbook_character_cards_translation_creates_immutable: str = '维护世界观和角色卡；翻译开始时会生成不可变上下文快照'
    onekey_loading_project_assets: str = '正在读取项目资产…'
    onekey_next_start_translation: str = '下一步 (开始翻译) →'
    onekey_run_ai_translation: str = '执行 AI 翻译'
    onekey_translation_files_written_separate_folder_under_game: str = (
        '翻译文件将输出到游戏根目录下的独立文件夹，不会被引擎识别。\n完成后可在「后续处理」中应用到游戏。'
    )
    onekey_start_translation: str = '🚀 开始翻译'
    onekey_recover_missed_text_after_translation_replace_text: str = '翻译完成后自动补全漏翻（replace_text）'
    onekey_disabled_default_when_enabled_second_pass_generates: str = (
        '默认关闭。\n开启后，主翻译完成会自动再跑一轮补全漏翻，生成/翻译 replace_text_auto.rpy。'
    )
    onekey_skip_translation: str = '跳过翻译 →'
    onekey_review_export_post_process: str = '检查、导出与后处理'
    onekey_select_game_folder: str = '选择游戏目录'
    onekey_no_extractable_files_found: str = '未检测到可提取的文件'
    onekey_extracting_text_game_creating_translation_files: str = '正在从游戏中提取文本并生成翻译文件，请稍候。'
    onekey_checking_game_files: str = '🔍 检测游戏状态...'
    onekey_character_candidates_variable_references_scanned: str = '已扫描角色候选(→角色工作台)和变量引用(→禁翻表)'
    onekey_translation_folders: str = '📁 翻译目录说明'
    onekey_b_input_folder_b_files_translate_br: str = (
        "<b>输入目录</b>（待翻译文件）：<br><code style='background:{code_bg};padding:2px 4px;'>{input_folder"
        "}</code><br><br><b>输出目录</b>（翻译结果）：<br><code style='background:{code_bg};padding:2px 4px;"
        "'>{output_folder}</code><br><br><p style='color:{hint_color};'><i>💡 输出目录位于游戏根目录下，不会被 Ren"
        "'Py 引擎识别。<br>翻译完成后，可在「后续处理」中应用到游戏。</i></p>"
    )
    onekey_confirm_translation_application: str = '确认应用翻译'
    onekey_b_apply_translation_game_b_br_br: str = (
        "<b>即将应用翻译到游戏</b><br><br><b>源目录：</b><br><code style='background:{code_bg};padding:2px 4px"
        ";'>{output_dir}</code><br><br><b>目标目录：</b><br><code style='background:{code_bg};padding:"
        "2px 4px;'>{input_dir}</code><br><br><b>文件数量：</b>{output_files_count} 个<br><br><p style='"
        "color:{warn_color};'><i>⚠️ 这将覆盖目标目录中的同名文件！<br>建议先备份原始文件。</i></p>"
    )
    onekey_apply_translation: str = '应用翻译'
    onekey_applying_translation_game: str = '正在应用翻译到游戏，请稍候…'
    onekey_translation_files_applied_but_cache_remains_try: str = '翻译文件已应用，但缓存仍保留在：{self_output_dir_cache}，请稍后重试应用。'
    onekey_back_toolbox: str = '返回工具箱'
    onekey_previous_step: str = '返回上一步'
    onekey_exit_wizard: str = '退出向导'
    onekey_translation_languages: str = '翻译语言设置'
    onekey_source_language: str = '游戏原语言'
    onekey_russian: str = '俄语'
    onekey_other: str = '其他'
    onekey_target_language: str = '翻译成'
    onekey_tl_folder_name: str = 'TL 文件夹名'
    onekey_existing_translation_detected_files: str = '🔍 检测到已有翻译 ({rpy_count} 个文件)'
    onekey_translation_files_already_exist_tl_choose_how: str = '该游戏在 tl/{tl_name} 中已有翻译文件，请选择处理方式：'
    onekey_select_valid_game_folder_first: str = '请先选择有效的游戏目录'
    onekey_could_not_locate_game_s_game_folder: str = '无法定位游戏的 game 目录'
    onekey_select_game_folder_first: str = '请先选择游戏目录'
    onekey_cleared: str = '清除完成'
    onekey_cleared_skipped_candidates: str = '已清除 {cleared} 条判定不译记录'
    onekey_there_no_skipped_candidates: str = '当前没有判定不译记录'
    onekey_glossary_do_not_translate_list: str = '术语表与禁翻表'
    onekey_glossary_keeps_proper_names_consistent_while_do: str = '术语表可以帮助你统一专有名词的翻译，禁翻表可以防止翻译不需要翻译的内容。本地词库页还支持手动扫描术语候选。'
    onekey_ready_translate: str = '准备翻译'
    onekey_translation_complete: str = '🎉 翻译已完成'
    onekey_you_can_now_review_complete_export_translation: str = '可继续检查、补全或导出翻译结果。'
    onekey_if_text_still_untranslated_game_use_recover: str = '如果切换到中文后仍有漏翻文本，优先使用“补全漏翻”生成 replace_text_auto.rpy。'
    onekey_review_polish_export: str = '检查、润色并导出'
    onekey_review_quality_reports_edit_selected_translations_export: str = '查看质量报告，校对或润色选中译文，然后导出翻译文件'
    onekey_recover_missed_text: str = '补全漏翻'
    onekey_find_text_missing_tl_generate_replace_text: str = '扫描 tl 未覆盖的文本并生成 replace_text_auto.rpy'
    onekey_detect_repair_errors: str = '检测/修复报错'
    onekey_fix_indentation_formatting_issues: str = '修复缩进和格式问题'
    onekey_set_default_language: str = '设置默认语言'
    onekey_set_language_used_when_game_starts: str = '设置游戏启动时的默认语言'
    onekey_add_language_switch: str = '添加语言切换'
    onekey_inject_language_switching_button: str = '注入语言切换按钮'
    onekey_inject_fonts: str = '批量注入字体'
    onekey_inject_bundled_font_pack: str = '注入预置字体包'
    onekey_open_game_folder: str = '打开游戏目录'
    onekey_view_translation_results: str = '查看翻译结果'
    onekey_export_language_patch: str = '导出语言补丁'
    onekey_export_tl_folder_zip_archive: str = '导出 tl 目录为 zip'
    onekey_open: str = '打开{title}'
    onekey_game_folder_not_found: str = '未找到 game 目录'
    onekey_found_rpa_archives_must_unpacked: str = '检测到 {rpa_count} 个 RPA 包，需要解包'
    onekey_found_rpyc_files_must_decompiled: str = '检测到 {rpyc_count} 个 RPYC 文件，需要反编译'
    onekey_found_rpy_files_rpyc_files: str = '检测到 {rpy_count} 个 RPY 和 {rpyc_count} 个 RPYC 文件'
    onekey_found_rpy_files_ready_extraction: str = '检测到 {rpy_count} 个 RPY 文件，可直接提取'
    onekey_decompilation_completed_unrpyc_v2: str = '反编译完成 (unrpyc v2)'
    onekey_extraction_already_running_wait_finish: str = '抽取正在进行中，请等待完成后再操作。'
    onekey_decompiling_rpyc_files: str = '🔨 正在反编译 RPYC 文件...'
    onekey_running_incremental_extraction: str = '🔄 增量抽取中...'
    onekey_extracting: str = '正在提取...'
    onekey_extraction_complete: str = '✓ 提取完成'
    onekey_new_content_written_existing_translations_left_unchanged: str = (
        '{msg}\n\n💡 新增内容已输出到单独文件夹：{name}/\n原有翻译保持不变，可分别处理新增内容。'
    )
    onekey_incremental_input_incremental_output: str = (
        '\n增量翻译输入：{name}/\n增量翻译输出：{name_2}/'
    )
    onekey_placeholders_preserved_new_old_you_can_translate: str = (
        '{msg}\n已保留占位（new==old），可直接进入翻译。需要更新术语/禁翻后可再次点击"重新抽取"。'
    )
    onekey_start_translation_2: str = '开始翻译 →'
    onekey_extraction_completed_character_names_variable_references_scanned: str = '提取完成，已自动扫描角色名和变量引用'
    onekey_extraction_failed: str = '✗ 提取遇到问题'
    onekey_error_select_extract_again_if_still_fails: str = (
        '错误信息：{msg}\n\n建议先点"重新抽取"。如仍失败，可跳过直接翻译，或检查路径/权限后再试。'
    )
    onekey_extraction_failed_you_can_try_again_skip: str = '提取过程遇到问题，你可以重试或跳过'
    onekey_found: str = '找到文件: {join_found_files}'
    onekey_no_glossary_files_found_default_configuration_used: str = '未找到术语表文件，将使用默认配置。'
    onekey_activate_translation_provider_configure_input_output_folders: str = '请先在接口设置激活翻译平台，并在项目设置填写输入/输出目录。'
    onekey_main_translation_complete_recovering_missed_text: str = '主翻译完成，正在自动补全漏翻…'
    onekey_translation_complete_continue_post_processing_apply_game: str = '✔ 翻译已完成，可直接进入「后续处理」应用翻译到游戏。'
    onekey_translate_again: str = '重新翻译'
    onekey_continue_post_processing: str = '进入后续处理 →'
    onekey_input_folder_missing_does_not_exist: str = '输入目录未设置或不存在'
    onekey_output_folder_not_configured: str = '输出目录未设置'
    onekey_no_translation_provider_active: str = '未激活翻译接口（请在接口设置启用平台）'
    onekey_ready_translate_2: str = '✔ 已准备好翻译，可直接开始。'
    onekey_output_folder_does_not_exist: str = '输出目录不存在：{output_dir}'
    onekey_target_folder_does_not_exist: str = '目标目录不存在：{input_dir}'
    onekey_output_folder_does_not_contain_translation_files: str = '输出目录中没有翻译文件（.rpy）'
    onekey_translation_already_being_applied_please_wait: str = '翻译应用正在进行中，请稍候…'
    onekey_translation_applied: str = '应用成功'
    onekey_export_complete: str = '导出完成'
    onekey_created_missing_translation_patch_entries: str = '已生成漏翻补丁：{patch_path}（{missing_count} 条）'
    onekey_failed_apply_translation: str = '应用翻译失败：{exc}'
    onekey_valid_ren_py_game_folder_detected: str = "✓ 检测到有效的 Ren'Py 游戏目录"
    onekey_no_game_subfolder_found_may_not_ren: str = "⚠ 目录中未找到 game 文件夹，可能不是 Ren'Py 游戏"
    onekey_game_file_selected: str = '✓ 已选择游戏文件'
    onekey_path_does_not_exist: str = '✗ 路径不存在'
    onekey_finish_translation_first: str = '请先完成翻译'
    onekey_incremental_content_has_not_been_applied_finish: str = '当前增量内容尚未应用，请完成翻译后返回工具箱，点击“应用翻译到游戏”。'
    onekey_merge_completed: str = '合并完成'
    onekey_merge_failed: str = '合并失败'
    onekey_decompilation_completed_unren: str = '反编译完成 (UnRen)'
    onekey_decompilation_failed_game_may_incompatible_encrypted_use: str = '反编译失败（可能版本不兼容/加密/脚本特殊）：{e}'
    onekey_running_decompiler_automatically: str = (
        '\n正在自动执行反编译，请稍候...'
    )
    onekey_decompilation_failed: str = '✗ 反编译失败'
    onekey_possible_causes_game_uses_encryption_obfuscation_ren: str = (
        "{decompile_msg}\n\n可能的原因：\n• 游戏使用了加密/混淆\n• Ren'Py 版本不兼容\n• 缺少游戏的 Python 运行时\n\n建议：尝试使用其他反编译工具或联"
        '系开发者'
    )
    onekey_decompilation_failed_check_game_files: str = '反编译失败，请检查游戏文件'
    onekey_rpa_archives_must_unpacked: str = '📦 需要解包 RPA'
    onekey_use_rpa_unpacker_first_when_finishes_return: str = (
        '{status_msg}\n\n请先使用「RPA 解包」功能解包游戏资源，\n解包完成后返回此页，点击「重新抽取」。'
    )
    onekey_unpack_rpa_archives_first: str = '请先解包 RPA 资源'
    onekey_unpacking_rpa_archives: str = '📦 正在解包 RPA 归档...'
    onekey_running_rpa_unpacker_automatically: str = (
        '\n正在自动执行解包，请稍候...（大体积游戏可能需要几分钟）'
    )
    onekey_unpack_failed: str = '✗ 解包失败'
    onekey_unpack_failed_hint: str = (
        '{unpack_msg}\n\n可能的原因：\n• RPA 归档损坏或不兼容\n• 缺少游戏自带的 Python 运行时\n• 外部解包工具不可用\n\n'
        '建议：点击「前往 RPA 解包」手动解包，或检查游戏文件后重试。'
    )
    onekey_unpack_complete_no_scripts: str = (
        '{unpack_msg}\n\n⚠ 解包完成后未检测到可提取的脚本（.rpy/.rpyc），请前往「RPA 解包」页检查解包结果。'
    )
    onekey_unpack_failed_check_game_files: str = '解包失败，请检查游戏文件'
    onekey_previous_incremental_cache_preserved_can_restored_manually: str = (
        '\n检测到上一轮增量缓存，已保存在：{name}/（未删除，可手动恢复）'
    )
    onekey_project_assets_currently_unavailable: str = '项目资产暂不可用：{exc}'
    onekey_character_world_workbench_page_not_found: str = '未找到角色/世界观工作台页面'
    onekey_could_not_open_workbench: str = '打开工作台失败：{exc}'
    onekey_could_not_open_translation_panel: str = '打开传统翻译面板失败: {e}'
    onekey_tl_folder_not_found_missed_text_recovery: str = '未找到 tl 目录，已跳过自动补全：{tl_dir}'
    onekey_could_not_start_missed_text_recovery: str = '自动补全漏翻启动失败: {e}'
    onekey_missed_text_recovery_did_not_finish_main: str = '自动补全漏翻未完成，已恢复主翻译路径。'
    onekey_missed_text_recovery_completed: str = '自动补全漏翻完成'
    onekey_complete_following_setup_first: str = (
        '⚠ 需先完成配置：\n'
    )
    onekey_could_not_open_missed_text_recovery: str = '打开补全翻译页面失败: {e}'
    onekey_could_not_open_error_repair: str = '打开错误修复页面失败：{exc}'
    onekey_select_game_folder_first_2: str = '请先选择游戏目录。'
    onekey_no_missing_translations_found_patch_not_needed: str = '未发现缺失翻译，无需生成补丁。'
    onekey_could_not_export_language_patch: str = '导出语言补丁失败：{exc}'
    onekey_decompilation_failed_unren_error: str = '反编译失败（UnRen 失败：{unren_error}）：{e}'
    onekey_game_files_not_found: str = '✗ 未找到游戏文件'
    onekey_output_folder_could_not_created: str = '输出目录无法创建'
    onekey_input_output_folders_must_different: str = '输入/输出目录不能相同'
    pack_unpack_invalid_part_size_enter_1g_1_5g: str = '分包上限格式不正确，请输入 1G、1.5G 或 1024M'
    pack_unpack_part_size_must_greater_than_0: str = '分包上限必须大于 0'
    pack_unpack_could_not_locate_game_folder_unren_fallback: str = '无法定位 game 目录用于 UnRen 兜底反编译'
    pack_unpack_could_not_locate_game_folder_rpyc_cleanup: str = '无法定位 game 目录用于清理 RPYC'
    pack_unpack_select_game_folder_containing_rpa_files: str = '选择包含 .rpa 文件的 game 目录'
    pack_unpack_direct_unpacking_unren_uses_game_s_python: str = '直接解包（UnRen：使用游戏自带 python，无需启动游戏）'
    pack_unpack_try_game_s_python_first_then_fall: str = '优先用游戏自带的 python 直接解包，失败会继续尝试外部工具'
    pack_unpack_scripts_only_rpy_rpyc_skip_images_audio: str = '仅解包脚本（.rpy/.rpyc；忽略图片/音频等资源，速度更快、体积更小）'
    pack_unpack_extract_script_files_only_faster_smaller_output: str = '只提取脚本文件，忽略图片/音频等资源，速度更快'
    pack_unpack_unpack: str = '解包'
    pack_unpack_clean_temporary_files: str = '清理临时文件'
    pack_unpack_select_folder_package: str = '选择要打包的目录'
    pack_unpack_leave_blank_use_folder_name_rpa_parent: str = '留空则使用目录名.rpa，保存在源目录的上级目录'
    pack_unpack_splitting_enabled_images_rpa_produces_images_part001: str = '启用分包后，例如 images.rpa 将生成 images.part001.rpa 等文件'
    pack_unpack_split_size: str = '按大小分包'
    pack_unpack_create_independent_part001_rpa_part002_rpa_similar: str = '生成名称为 .part001.rpa、.part002.rpa 的多个独立 RPA 文件'
    pack_unpack_e_g_1g_1024m: str = '如 1G 或 1024M'
    pack_unpack_supports_1g_1_5g_1024m_1024mib_values: str = '支持 1G、1.5G、1024M、1024MiB；不写单位时按 MiB'
    pack_unpack_pack: str = '打包'
    pack_unpack_select_game_folder_project_root_launcher_exe: str = '选择 game 目录（或根目录/启动程序 .exe）'
    pack_unpack_overwrite_existing_rpy_files_unrpyc_clobber: str = '覆盖已存在的 .rpy (unrpyc --clobber)'
    pack_unpack_direct_decompilation_unren_uses_game_s_python: str = '直接反编译（UnRen：使用游戏自带 python，无需启动游戏）'
    pack_unpack_try_unren_first_then_fall_back_unrpyc: str = '优先使用 UnRen 执行反编译，失败再尝试 unrpyc'
    pack_unpack_decompile: str = '反编译'
    pack_unpack_try_unren_first_then_fall_back_unrpyc_2: str = '优先使用 UnRen 反编译，失败再尝试 unrpyc v2'
    pack_unpack_clean_rpyc_files: str = '清理 RPYC 文件'
    pack_unpack_delete_rpyc_files_have_matching_decompiled_rpy: str = '删除 game 目录内已成功反编译的 RPYC 文件'
    pack_unpack_select_game_folder: str = '选择 game 目录'
    pack_unpack_select_folder_package_2: str = '选择要打包的目录'
    pack_unpack_select_rpa_output_base_file: str = '选择 RPA 输出基准文件'
    pack_unpack_rpa_files_rpa: str = 'RPA 文件 (*.rpa)'
    pack_unpack_select_game_folder_project_root: str = '选择 game 目录（或项目根目录）'
    pack_unpack_scanning_files: str = '正在扫描文件...'
    pack_unpack_packing: str = '打包中: {current}/{total} - {filename}'
    pack_unpack_packaging_complete_generated_rpa_file_s: str = '打包完成，共生成 {output_paths_count} 个 RPA 文件'
    pack_unpack_unpacking: str = '正在解包…'
    pack_unpack_trying_unren_fallback: str = '尝试 UnRen 兜底解包…'
    pack_unpack_decompiling: str = '正在反编译…'
    pack_unpack_cleaning_temporary_files: str = '正在清理临时文件…'
    pack_unpack_cleaning_rpyc_files: str = '正在清理 RPYC 文件…'
    pack_unpack_removed_rpyc_file_s: str = '已清理 {removed} 个 RPYC 文件'
    pack_unpack_no_rpyc_files_found: str = '未发现 RPYC 文件'
    pack_unpack_unpack_decompile_pack: str = '📦 解包 / 反编译 / 打包'
    pack_unpack_unpack_rpa_files: str = '📂 解包 RPA 文件'
    pack_unpack_game_folder: str = 'game 目录:'
    pack_unpack_pack_rpa_files: str = '📦 打包为 RPA 文件'
    pack_unpack_source_folder: str = '源目录:'
    pack_unpack_output_base_file: str = '输出基准文件:'
    pack_unpack_maximum_per_part: str = '每包上限:'
    pack_unpack_decompile_rpyc_rpy: str = '🧩 反编译 RPYC → RPY'
    pack_unpack_game_folder_executable: str = 'game 目录/可执行文件:'
    pack_unpack_preparing: str = '准备开始…'
    pack_unpack_preparing_cleanup: str = '准备清理…'
    pack_unpack_select_source_folder: str = '请选择源目录'
    pack_unpack_source_folder_does_not_exist: str = '源目录不存在'
    pack_unpack_packaging_task_already_running: str = '打包任务正在进行中'
    pack_unpack_cancelling_after_current_part_finishes_writing: str = '正在取消，当前分包写完后停止...'
    pack_unpack_no_rpa_files_found_external_tools_unren: str = '未找到 RPA 文件，或外部工具/UnRen 不可用'
    pack_unpack_decompiling_unren: str = '正在使用 UnRen 反编译…'
    pack_unpack_decompilation_complete_generated_rpy_files: str = '反编译完成，已生成 .rpy 文件'
    pack_unpack_unren_failed: str = '（UnRen 失败：{unren_error}）'
    pack_unpack_skipped_file_s_without_matching_rpy_files: str = '，跳过 {skipped} 个未找到同名 .rpy 的文件'
    pack_unpack_no_removable_rpyc_files_found_because_matching: str = '未发现可清理的 RPYC 文件（未找到同名 .rpy）'
    pack_unpack_no_removable_rpyc_files_found: str = '未发现可清理的 RPYC 文件'
    pack_unpack_unpacking_task_already_running: str = '解包任务正在进行中'
    pack_unpack_select_game_folder_2: str = '请选择 game 目录'
    pack_unpack_unpacking_failed: str = '解包失败: {e}'
    pack_unpack_cleanup_task_already_running: str = '清理任务正在进行中'
    pack_unpack_decompilation_task_already_running: str = '反编译任务正在进行中'
    pack_unpack_cleanup_failed: str = '清理失败: {e}'
    pack_unpack_select_game_folder_project_root_executable: str = '请选择 game 目录（或根目录/可执行文件）'
    pack_unpack_path_does_not_exist: str = '路径不存在'
    pack_unpack_decompilation_failed: str = '反编译失败: {e}'
    pack_unpack_cleanup_failed_2: str = '清理失败: {exc}'
    pack_unpack_unavailable: str = '打包工具不可用'
    pack_unpack_trying_direct_unpacking: str = '正在尝试直接解包…'
    pack_unpack_unpacked_rpa_file_s: str = '已解包 {count} 个 RPA 文件'
    pack_unpack_unpacked_unren_fallback_check_game_folder_output: str = '已使用 UnRen 兜底解包（请检查 game 目录输出）'
    pack_unpack_unpacking_failed_2: str = '解包失败: {exc}'
    pack_unpack_error_generic: str = '解包失败，请查看日志了解详情。'

    @classmethod
    def pack_unpack_error(cls, code: str) -> str:
        """按稳定 code 返回解包失败文案；未知 code 走通用兜底。"""
        return _PACK_UNPACK_ERROR_ZH.get(str(code or ""), cls.pack_unpack_error_generic)
    pack_unpack_decompilation_failed_2: str = '反编译失败: {exc}{extra}'
    pack_unpack_removed_temporary_item_s: str = '已清理 {removed} 个临时项'
    pack_unpack_no_temporary_files_need_cleaned: str = '未发现需要清理的临时文件'
    pack_unpack_cancelled: str = '已取消'
    pack_unpack_packaging_failed: str = '打包失败: {message}'
    pack_unpack_direct_unpacking_failed_trying_external_tools: str = '直接解包失败，尝试使用外部工具继续解包…'
    pack_unpack_decompilation_completed_unren: str = '反编译完成（UnRen）'
    pack_unpack_directly_unpacked_archive_s: str = '已直接解包 {count} 个归档文件'
    toolbox_search_tools: str = '搜索工具'
    toolbox_no_matching_tools: str = '没有匹配的工具'
    toolbox_try_another_keyword_clear_search_box: str = '换个关键词试试，或清空搜索框'
    toolbox_select_game_folder_first: str = '需先选择游戏目录'
    toolbox_unknown_tool: str = '未知工具入口: {key}'
    toolbox_tool_has_no_configured_page: str = '工具 {key} 未配置页面'
    toolbox_game_folder_not_selected: str = '未选择游戏目录'
    toolbox_select_game_folder_one_click_translation_first: str = '请先在「一键翻译」中选择游戏目录'
    toolbox_failed_open: str = '打开失败'
    toolbox_could_not_open: str = '无法打开「{title}」: {exc}'
    toolbox_failed_open_translation_panel: str = '打开翻译面板失败: {exc}'
    default_language_select_project_root_containing_game: str = '选择项目根目录（包含 game/ 的上级目录）'
    default_language_leave_blank_use_selected_language: str = '留空则使用上方选择的语言'
    default_language_sets_language_used_when_game_starts_steps: str = (
        "此功能将设置游戏启动时使用的默认语言。\n\n操作步骤：\n1. 选择项目根目录\n2. 选择或输入默认语言名称（必须与 tl 目录下的语言目录名一致）\n3. 点击'设置默认语言'按钮"
        '\n\n注意：语言名称必须与 game/tl/ 下的目录名完全一致'
    )
    default_language_select_project_root: str = '选择项目根目录'
    default_language_set_default_language: str = '🌍 设置默认语言'
    default_language_default_language: str = '🗣️ 默认语言'
    default_language_default_language_2: str = '默认语言:'
    default_language_custom_name: str = '自定义名称:'
    default_language_default_language_script_created: str = '默认语言脚本已生成: {name}'
    default_language_select_project_folder: str = '请选择项目目录'
    default_language_select_enter_language_name: str = '请选择或输入语言名称'
    default_language_language_folder_not_found_make_sure_translations: str = (
        '未找到语言目录: {tl_dir}\n请确保已创建该语言的翻译'
    )
    default_language_template_missing: str = '缺少模板: {template}'
    default_language_failed_set_default_language: str = '设置默认语言失败: {e}'
    text_preserve_do_not_translate: str = '🚫 文本保留管理'
    text_preserve_manage_text_should_remain_unchanged_during_translation: str = '管理不需要翻译的文本（如专有名词、代码片段等），这些内容将在翻译过程中保持原文。'
    text_preserve_save_settings: str = '保存到配置'
    text_preserve_load_settings: str = '从配置加载'
    text_preserve_deduplicate: str = '去重'
    text_preserve_deduplicate_source_text_merge_notes_prefer_rows: str = '按原文去重，合并备注，优先保留有备注的行'
    text_preserve_delete_all_do_not_translate_entries_save: str = '删除所有保留文本并写入配置'
    text_preserve_count_how_many_cached_output_entries_match: str = '基于当前 output/cache 中的缓存条目统计每条禁翻规则命中的文本数量'
    text_preserve_rescan_variables: str = '重新扫描变量'
    text_preserve_scan_game_folder_variable_references_replace_previous: str = '扫描游戏目录，自动提取[variable]变量引用（清空旧数据）'
    text_preserve_do_not_translate_entries_cells_editable: str = '保留文本列表（可直接编辑单元格）'
    text_preserve_deleted_all_do_not_translate_entries_saved: str = '已删除所有保留文本并写入配置'
    text_preserve_loaded_do_not_translate_entries_settings: str = '已从配置加载 {converted_count} 条保留文本'
    text_preserve_saved_do_not_translate_entries_settings: str = '已写入 {entries_count} 条保留文本到配置'
    text_preserve_select_excel_file: str = '选择 Excel 文件'
    text_preserve_save_excel_file: str = '保存 Excel'
    text_preserve_analyzed_rules_across_cached_entries: str = '已统计 {counts_count} 条禁翻规则，样本条目 {counted_item_total} 条'
    text_preserve_found_variable_references_scanned: str = '已扫描到 {new_preserves_count} 个变量引用（扫描目录：{game_path}）'
    text_preserve_imported_do_not_translate_entries: str = '已导入 {items_count} 条保留文本'
    text_preserve_there_no_do_not_translate_entries_analyze: str = '当前禁翻表为空，暂无可统计的数据'
    text_preserve_entries_changed_run_statistics_again: str = '禁翻表内容已变化，请重新执行一次统计'
    text_preserve_no_folder_available_scan_set_input_output: str = '未找到可扫描目录，请先设置输入/输出目录或游戏目录'
    text_preserve_could_not_determine_which_folder_scan: str = '无法确定扫描目录'
    text_preserve_no_variable_references_found_list_cleared_scanned: str = '未找到变量引用，已清空禁翻表（扫描目录：{game_path}）'
    text_preserve_source_column_not_found_check_template: str = '未找到“原文”列，请确认模板。'
    text_preserve_scan_failed: str = '扫描失败: {e}'
    extract_tl_translation_extraction: str = '翻译抽取'
    extract_tl_extract_translatable_text_ren_py_game_tl: str = "从 Ren'Py 游戏中提取可翻译文本到 tl 目录"
    extract_tl_select_game_project_folder_contains_game_directory: str = '选择游戏文件夹（包含 game 目录的那个）'
    extract_tl_translation_folder_name_such_chinese_schinese: str = '翻译文件夹名称，如 chinese、schinese 等'
    extract_tl_start_extraction: str = '开始抽取'
    extract_tl_existing_translations_preserved_default_supplemental_extraction_works: str = '默认保留已有翻译（增量），未找到 exe 也能用补充抽取；官方抽取失败可仅用补充抽取。'
    extract_tl_advanced_options: str = '▶ 高级选项'
    extract_tl_official_extraction: str = '官方抽取'
    extract_tl_use_game_engine_s_official_translation_extraction: str = '调用游戏引擎的官方翻译抽取（需要 exe）'
    extract_tl_supplemental_extraction: str = '补充抽取'
    extract_tl_use_custom_ast_parsing_extract_text_missed: str = '自定义 AST 解析，覆盖官方遗漏的文本'
    extract_tl_only_required_official_extraction_leave_blank_find: str = '仅勾选官方抽取时需要，留空自动查找 .exe'
    extract_tl_skip_hook_files: str = '跳过 Hook 文件'
    extract_tl_filter_suspected_code_entries: str = '过滤疑似代码条目'
    extract_tl_back_up_filtered_entries_filtered_suspicious_so: str = '会备份到 _filtered_suspicious，可手动勾选恢复'
    extract_tl_merge_incremental_results_remove_duplicates_automatically: str = '抽取后自动合并并清理重复'
    extract_tl_merge_remove_duplicates: str = '合并并清理重复'
    extract_tl_open_filtered_backup: str = '打开误提取备份'
    extract_tl_restore_selected_entries: str = '恢复误提取勾选项'
    extract_tl_suspected_code_lines_moved_tl_lang_filtered: str = '抽取后会把疑似代码行移到 tl/<lang>/_filtered_suspicious/<时间戳>/restore_manifest.csv；把 restore 列改为 1 后可一键恢复。'
    extract_tl_select_game_executable: str = '选择游戏可执行文件'
    extract_tl_executable_files_exe_py: str = '可执行文件 (*.exe *.py)'
    extract_tl_game_folder: str = '游戏目录:'
    extract_tl_language_name: str = '语言名称:'
    extract_tl_extraction_method: str = '抽取方式:'
    extract_tl_game_exe_optional: str = '游戏 exe (可选):'
    extract_tl_advanced_options_2: str = '▼ 高级选项'
    extract_tl_extracting_translatable_text: str = '正在抽取翻译文本...'
    extract_tl_merging_incremental_translations: str = '正在合并增量翻译...'
    extract_tl_no_filtered_backup_available_yet: str = '还没有误提取备份记录'
    extract_tl_restoring_filtered_entries: str = '正在恢复误提取条目...'
    extract_tl_folder_does_not_exist: str = '目录不存在: {game_dir}'
    extract_tl_game_directory_not_found: str = '未找到 game 目录'
    extract_tl_tl_subfolder_not_found: str = '未找到 tl 子目录: {tl_dir}'
    extract_tl_no_exe_found_official_extraction_disabled_supplemental: str = '未找到 exe，已自动关闭官方抽取，改用补充抽取'
    extract_tl_incremental_mode: str = '增量模式'
    extract_tl_existing_tl_files_found_incremental_extraction_preserve: str = '检测到已有 tl，增量抽取会保留已翻译内容'
    extract_tl_extraction_complete: str = '抽取完成'
    extract_tl_extraction_failed: str = '抽取失败'
    extract_tl_merge_complete: str = '合并完成'
    extract_tl_restore_complete: str = '恢复完成'
    extract_tl_nothing_restored: str = '未恢复'
    extract_tl_leave_blank_find_exe_automatically: str = '留空自动查找 .exe'
    extract_tl_automatic_merge_complete: str = '自动合并完成'
    extract_tl_automatic_merge_failed: str = '自动合并失败'
    extract_tl_failed_read_default_encoding: str = (
        '默认编码读取失败: {renpy_default_encoding}\n{e}'
    )
    workbench_not_configured: str = '未配置'
    workbench_not_set: str = '未设置'
    workbench_latest_analysis_source: str = '最近分析来源：{source_summary}'
    workbench_character_sync_source: str = '角色同步来源：{payload_get_source_summary}'
    workbench_character_sync_complete_new_drafts_ready_review: str = '角色同步完成，共新增 {added} 张待确认草稿。'
    workbench_manage_worldbuilding_character_profiles_prompt_context_current: str = '在这里维护当前输出项目的世界观、人设和提示词上下文，并可手动触发 AI 生成草稿。'
    workbench_current_project_summary: str = '当前项目摘要'
    workbench_single_view_current_api_paths_workbench_state: str = '这里聚合当前接口、路径、工作台状态和草稿状态，作为主入口总览。'
    workbench_analysis_shortcuts: str = '分析与跳转'
    workbench_generate_ai_drafts_demand_current_scope_then: str = '默认手动触发 AI 生成；支持先当前范围，再扩展到全项目重分析。'
    workbench_generate_current_scope_drafts: str = '生成当前范围草稿'
    workbench_reanalyze_full_project: str = '扩展到全项目重分析'
    workbench_sync_character_names: str = '同步角色名'
    workbench_apply_all_drafts: str = '应用全部草稿'
    workbench_apply_all_and_enable: str = '应用全部并启用'
    workbench_import_as_drafts: str = '导入为待审核'
    workbench_import_apply_enable: str = '导入并启用'
    workbench_export_project_assets: str = '导出项目资料'
    workbench_clear_current_characters: str = '清空当前项目角色'
    workbench_open_local_glossary: str = '打开本地词库'
    workbench_open_do_not_translate_list: str = '打开禁翻表'
    workbench_open_custom_prompts: str = '打开自定义提示词'
    workbench_ready: str = '等待操作'
    workbench_worldbuilding: str = '世界观设定'
    workbench_edit_approved_worldbuilding_left_review_ai_drafts: str = '左侧维护正式世界观，右侧查看 AI 草稿与原始响应预览。'
    workbench_inject_worldbuilding_context: str = '启用世界观上下文注入'
    workbench_approved_worldbuilding: str = '正式世界观'
    workbench_content_inserted_directly_generated_prompts: str = '这些内容会直接进入提示词构建。'
    workbench_ai_draft_preview: str = 'AI 草稿预览'
    workbench_generated_content_remains_draft_until_you_apply: str = '生成成功后只进入草稿区，确认后再应用。'
    workbench_generate_current_scope: str = '生成当前范围'
    workbench_expand_reanalyze: str = '扩展重分析'
    workbench_apply_worldbuilding_draft: str = '应用世界观草稿'
    workbench_generated_worldbuilding_drafts_appear_here: str = '生成后在这里查看世界观草稿。'
    workbench_if_parsing_fails_raw_model_response_appears: str = '解析失败时，这里会显示模型原始响应。'
    workbench_character_card_workbench: str = '角色卡工作台'
    workbench_browse_characters_left_edit_approved_cards_center: str = '左侧角色列表，中间正式角色卡，右侧 AI 草稿与原始响应。'
    workbench_inject_character_card_context: str = '启用角色卡上下文注入'
    workbench_generate_all_character_cards: str = '整批生成角色卡'
    workbench_regenerate_current_character: str = '重新生成当前角色'
    workbench_apply_current_character_draft: str = '应用当前角色草稿'
    workbench_apply_current_and_enable: str = '应用当前并启用'
    workbench_add_blank_character_card: str = '新增空白角色卡'
    workbench_delete_current_character: str = '删除当前角色'
    workbench_character_list: str = '角色列表'
    workbench_synced_character_candidates_added_here_review: str = '同步角色名后，会把候选角色预填到这里。'
    workbench_search_characters: str = '搜索角色名、别名或关键词'
    workbench_filter_all: str = '全部'
    workbench_filter_pending: str = '待审核'
    workbench_filter_applied: str = '已应用'
    workbench_character_count: str = '显示 {visible} / {total} 张'
    workbench_approved_character_card: str = '正式角色卡'
    workbench_manual_edits_saved_immediately_current_project_assets: str = '手工修改后会立即写入当前项目资产。'
    workbench_enable_character_card: str = '启用此角色卡'
    workbench_mark_main_character: str = '标记为主要角色'
    workbench_character_draft_preview: str = '角色草稿预览'
    workbench_ai_generated_character_drafts_appear_here: str = 'AI 生成的人设草稿会显示在这里。'
    workbench_select_character_view_draft_details: str = '选择角色后，这里显示草稿详情。'
    workbench_if_parsing_fails_raw_model_response_appears_2: str = '解析失败时，这里显示模型原始响应。'
    workbench_prompt_match_preview: str = '提示词命中预览'
    workbench_enter_sample_source_text_preview_matching_character: str = '输入样例原文后，会实时显示命中的角色卡和最终注入片段。'
    workbench_enter_one_more_lines_sample_source_text: str = '在这里输入一段样例原文，支持多行。'
    workbench_no_sample_source_text_entered: str = '未输入样例原文。'
    workbench_injected_context: str = '注入结果'
    workbench_preview_how_workbench_context_inserted_final_prompt: str = '这里展示工作台上下文如何进入真实提示词构建。'
    workbench_worldbuilding_context_appears_here: str = '世界观块将在这里显示。'
    workbench_matched_character_context_appears_here: str = '命中角色块将在这里显示。'
    workbench_final_injected_context_appears_here: str = '最终注入片段将在这里显示。'
    workbench_enabled: str = '已启用'
    workbench_not_enabled: str = '未启用'
    workbench_total_enabled: str = '共 {cards_count} 张，启用 {enabled_cards} 张'
    workbench_unnamed_character: str = '未命名角色'
    workbench_none: str = '暂无'
    workbench_character: str = '角色{len_cards}'
    workbench_running_ai_analysis: str = '正在执行 AI 分析...'
    workbench_ai_drafts_ready_review_them_right_before: str = 'AI 草稿已生成，请在右侧预览并决定是否应用。'
    workbench_ai_draft_generation_complete: str = 'AI 草稿生成完成。'
    workbench_syncing_character_candidates: str = '正在同步角色候选...'
    workbench_worldbuilding_draft_has_been_applied: str = '世界观草稿已应用。'
    workbench_character_draft_has_been_applied: str = '当前角色草稿已应用。'
    workbench_all_drafts_have_been_applied: str = '全部草稿已应用。'
    workbench_character_worldbuilding_workbench: str = '角色 / 世界观工作台'
    workbench_overview: str = '概览'
    workbench_worldbuilding_2: str = '世界观'
    workbench_character_cards: str = '角色卡'
    workbench_prompt_preview: str = '提示词预览'
    workbench_current_api: str = '当前接口'
    workbench_current_model: str = '当前模型'
    workbench_language_pair: str = '语言方向'
    workbench_input_folder: str = '输入目录'
    workbench_output_folder: str = '输出目录'
    workbench_project_folder: str = '项目目录'
    workbench_tl_folder: str = 'TL 目录'
    workbench_draft_status: str = '草稿状态'
    workbench_project_name: str = '项目名'
    workbench_genre: str = '类型'
    workbench_setting_summary: str = '背景摘要'
    workbench_era_environment: str = '时代与环境'
    workbench_tone_style: str = '整体语气'
    workbench_narrative_rules: str = '叙事规则'
    workbench_formatting_rules: str = '格式规则'
    workbench_spoiler_notes: str = '剧透备注'
    workbench_reference_notes: str = '补充参考资料'
    workbench_structured_draft: str = '结构化草稿'
    workbench_raw_response_error_preview: str = '原始响应 / 错误预览'
    workbench_character_name: str = '角色名'
    workbench_suggested_translation: str = '推荐译名'
    workbench_aliases: str = '别名'
    workbench_match_keywords: str = '匹配关键词'
    workbench_identity: str = '身份'
    workbench_personality: str = '性格'
    workbench_speech_style: str = '说话风格'
    workbench_relationship_notes: str = '关系备注'
    workbench_translation_notes: str = '翻译提示'
    workbench_sample_lines: str = '代表台词'
    workbench_worldbuilding_context: str = '世界观块'
    workbench_character_context: str = '角色块'
    workbench_final_injected_context: str = '最终注入片段'
    workbench_no_ai_analysis_has_been_run_yet: str = '当前尚未执行 AI 分析。'
    workbench_project_name_2: str = '项目名：{draft_get_project_name}'
    workbench_genre_2: str = '类型：{draft_get_genre}'
    workbench_setting_summary_2: str = '背景摘要：{draft_get_setting_summary}'
    workbench_era_environment_2: str = '时代与环境：{draft_get_era_background}'
    workbench_tone_style_2: str = '整体语气：{draft_get_tone_style}'
    workbench_narrative_rules_2: str = '叙事规则：{draft_get_narrative_rules}'
    workbench_formatting_rules_2: str = '格式规则：{draft_get_format_rules}'
    workbench_spoiler_notes_2: str = '剧透备注：{draft_get_spoiler_notes}'
    workbench_reference_notes_preview: str = '补充参考资料：{reference_notes}'
    workbench_character_name_2: str = '角色名：{draft_get_name}'
    workbench_suggested_translation_2: str = '推荐译名：{draft_get_name_translation}'
    workbench_identity_2: str = '身份：{identity_or_empty_value}'
    workbench_personality_2: str = '性格：{personality_or_empty_value}'
    workbench_speech_style_2: str = '说话风格：{speech_style_or_empty_value}'
    workbench_relationship_notes_2: str = '关系备注：{relationship_notes_or_empty_value}'
    workbench_translation_notes_2: str = '翻译提示：{prompt_notes_or_empty_value}'
    workbench_translation_task_running_ai_generation_character_sync: str = '当前翻译任务运行中，AI 生成与角色同步已暂时禁用。'
    workbench_ai_analysis_failed: str = 'AI 分析失败'
    workbench_there_no_worldbuilding_draft_apply: str = '当前没有可应用的世界观草稿。'
    workbench_select_character_first: str = '请先选择一个角色。'
    workbench_selected_character_has_no_draft_apply: str = '当前角色没有可应用的草稿。'
    workbench_there_no_drafts_apply: str = '当前没有可应用的草稿。'
    workbench_ren_py_toolbox_page_unavailable: str = "未找到 Ren'Py 工具箱页面。"
    workbench_main: str = '主'
    workbench_off: str = '关'
    workbench_draft: str = '草稿'
    workbench_sample_lines_2: str = '代表台词：'
    workbench_current_api_does_not_support_ai_analysis: str = '当前接口不支持 AI 分析。请切换到 OpenAI / Google / Anthropic / SakuraLLM 类接口。'
    workbench_ai_analysis_running_please_wait: str = 'AI 分析进行中，请稍候。'
    workbench_character_sync_running_please_wait: str = '角色同步进行中，请稍候。'
    workbench_ai_analysis_failed_2: str = 'AI 分析失败。'
    workbench_unknown_analysis_mode: str = '未知的分析模式。'
    workbench_select_import_file: str = '导入工作台项目资料'
    workbench_select_export_file: str = '导出工作台项目资料'
    workbench_json_file_filter: str = 'JSON 文件 (*.json)'
    workbench_import_failed: str = '导入失败：{error}'
    workbench_imported_as_drafts: str = '已导入 {count} 张角色卡，资料保存在待审核草稿中。'
    workbench_import_applied: str = '已导入 {count} 张角色卡，并启用项目提示词注入。'
    workbench_export_failed: str = '导出失败：{error}'
    workbench_export_complete: str = '项目资料已导出到：{path}'
    workbench_no_characters_to_clear: str = '当前项目没有可清理的角色资料。'
    workbench_clear_current_characters_confirm: str = '将删除当前项目的 {cards} 张正式角色卡和 {drafts} 张待审核草稿；世界观、术语表和其他项目不会受影响。建议先导出备份。是否继续？'
    workbench_current_characters_cleared: str = '当前项目的角色资料已清空。'

    # 通用界面补充
    error: str = "错误"
    success: str = "成功"
    complete: str = "完成"
    notice: str = "提示"
    browse: str = "浏览"
    ready: str = "等待操作"
    enabled: str = "已启用"
    disabled: str = "未启用"
    available: str = "有"
    current_scope: str = "当前范围"
    full_project: str = "全项目"
    list_separator: str = "、"
    rule_statistics_no_cached_entries: str = "未找到缓存条目。请先运行翻译，或检查当前输出缓存。"
    rule_statistics_unavailable: str = "无法计算命中统计。"

    # 未自动迁移的动态工具文案
    android_build_environment_check_completed: str = "环境检查完成"
    android_build_environment_check_failed: str = "环境检查失败"
    android_build_sdk_installation_completed: str = "SDK 安装完成"
    android_build_sdk_installation_failed: str = "SDK 安装失败"
    android_build_signing_key_generated: str = "签名生成完成"
    android_build_signing_key_generation_failed: str = "签名生成失败"
    font_replace_font_pack_injected_into_tl: str = "字体包已注入 tl/{target_lang}。"
    font_replace_modified_files_with_replacements: str = (
        "已修改 {replaced_files} 个文件，共完成 {replaced_count} 处替换。{backup_info}"
    )
    local_glossary_translation_failed_check_engine_logs: str = "术语库翻译失败，请检查当前翻译接口和日志。"
    local_glossary_scanning_term_candidates_percent: str = "正在扫描术语候选... {percent}%"
    local_glossary_candidate_scan_failed_check_folder_logs: str = "术语候选扫描失败，请检查所选目录和日志。"
    local_glossary_no_usable_term_candidates_generated: str = "未生成可用的术语候选。"
    local_glossary_scan_steps_reported_warnings: str = "\n部分扫描步骤报告了警告。"
    onekey_extracting_text: str = "正在提取文本..."
    onekey_text_extraction_completed: str = "文本提取完成"
    onekey_text_extraction_failed: str = "文本提取失败"
    onekey_text_extraction_failed_with_error: str = "文本提取失败：{error}"
    onekey_applying_translation: str = "正在应用翻译..."
    onekey_incremental_translation_merge_failed: str = "增量翻译文件合并失败"
    onekey_incremental_translation_applied: str = "增量翻译已成功应用"
    onekey_incremental_files_merged: str = "增量文件已合并并清理重复项"
    onekey_incremental_files_merge_failed: str = "无法合并增量文件"
    onekey_project_assets_summary: str = (
        "当前项目资产：世界观{worldbook_status}，角色卡 {character_count} 张，术语 {glossary_count} 项，"
        "禁翻 {preserve_count} 项；待确认术语候选 {candidate_count} 项，角色草稿 {draft_count} 张。"
    )
    extract_tl_incremental_results_merged: str = "增量结果已成功合并。"
    extract_tl_incremental_results_merge_failed: str = "增量结果合并失败。"
    extract_tl_translation_extraction_completed: str = "翻译文本提取完成。"
    extract_tl_translation_extraction_failed: str = "翻译文本提取失败。"
    extract_tl_entries_restored: str = "已恢复勾选的条目。"
    extract_tl_no_entries_restored: str = "没有恢复任何条目。"
    workbench_draft_summary: str = (
        "世界观草稿：{worldbook_status}；角色草稿：{draft_count} 张；最近范围：{scope}"
    )
    workbench_aliases_preview: str = "别名：{aliases}"
    workbench_match_keywords_preview: str = "匹配关键词：{keywords}"
    workbench_matched_characters: str = "命中角色：{names}"

    # 工具箱入口注册表
    toolbox_group_flow: str = "推荐流程"
    toolbox_group_translate: str = "翻译方式"
    toolbox_group_asset: str = "资源与词表"
    toolbox_group_engineer: str = "工程与修复"
    toolbox_tool_continue_translation_title: str = '继续翻译'
    toolbox_tool_continue_translation_description: str = '检测到上次未完成的翻译任务'
    toolbox_tool_one_key_translate_title: str = '一键翻译'
    toolbox_tool_one_key_translate_description: str = '选择游戏目录，自动完成抽取和翻译'
    toolbox_tool_proofreading_title: str = '检查与润色'
    toolbox_tool_proofreading_description: str = '查看质量报告、校对或润色译文并导出'
    toolbox_tool_apply_translation_title: str = '应用翻译到游戏'
    toolbox_tool_apply_translation_description: str = '将翻译结果写入游戏的 TL 目录'
    toolbox_tool_font_replace_title: str = '字体注入'
    toolbox_tool_font_replace_description: str = '注入预置字体包及对应的界面适配脚本'
    toolbox_tool_add_language_title: str = '添加语言入口'
    toolbox_tool_add_language_description: str = '向游戏添加语言切换功能'
    toolbox_tool_set_default_language_title: str = '设置默认语言'
    toolbox_tool_set_default_language_description: str = '设置游戏启动时的默认语言'
    toolbox_tool_extract_to_tl_title: str = '翻译抽取到 TL'
    toolbox_tool_extract_to_tl_description: str = '使用官方抽取、运行时抽取等高级抽取方式'
    toolbox_tool_direct_rpy_translate_title: str = '直接翻译 RPY'
    toolbox_tool_direct_rpy_translate_description: str = '直接翻译 tl/*.rpy 文件'
    toolbox_tool_hook_translate_title: str = 'HOOK 翻译'
    toolbox_tool_hook_translate_description: str = '运行游戏并抽取文本后直接翻译'
    toolbox_tool_source_translate_title: str = '源码翻译'
    toolbox_tool_source_translate_description: str = '直接翻译 game/*.rpy 源码'
    toolbox_tool_hook_supplement_title: str = '补全翻译'
    toolbox_tool_hook_supplement_description: str = '扫描漏提文本并生成补全脚本'
    toolbox_tool_extract_json_title: str = '文本提取 JSON'
    toolbox_tool_extract_json_description: str = '导出 JSON 供人工翻译，再导入并应用到 TL'
    toolbox_tool_local_glossary_title: str = '本地词库'
    toolbox_tool_local_glossary_description: str = '管理术语表，统一专有名词翻译'
    toolbox_tool_text_preserve_title: str = '禁翻表'
    toolbox_tool_text_preserve_description: str = '管理不需要翻译的变量和代码'
    toolbox_tool_honorific_placeholder_title: str = '称呼桥接'
    toolbox_tool_honorific_placeholder_description: str = '处理称呼和变量组合文本'
    toolbox_tool_ma_suite_title: str = '终极结构导出'
    toolbox_tool_ma_suite_description: str = '导出 Excel 和结构化翻译脚本'
    toolbox_tool_batch_correction_title: str = '批量修正'
    toolbox_tool_batch_correction_description: str = '通过 Excel 批量修正质检报告中的译文'
    toolbox_tool_name_extraction_title: str = '姓名提取'
    toolbox_tool_name_extraction_description: str = '扫描脚本与 JSON，生成角色名清单'
    toolbox_tool_pack_unpack_title: str = '解包/打包'
    toolbox_tool_pack_unpack_description: str = '解包 RPA 文件或打包游戏资源'
    toolbox_tool_error_repair_title: str = '错误修复'
    toolbox_tool_error_repair_description: str = '扫描并修复常见脚本错误'
    toolbox_tool_translation_reuse_title: str = '更新翻译复用'
    toolbox_tool_translation_reuse_description: str = '按原文将旧译文安全填入新版本的空条目'
    toolbox_tool_formatter_title: str = '代码格式化'
    toolbox_tool_formatter_description: str = '格式化 .rpy 文件'
    toolbox_tool_android_build_title: str = '安卓打包'
    toolbox_tool_android_build_description: str = '安装 SDK、生成签名并构建 APK'
    toolbox_tool_html_import_title: str = 'HTML 导入'
    toolbox_tool_html_import_description: str = '在 HTML、TXT 与 Excel 之间转换翻译文本'
    toolbox_tool_game_mod_title: str = '游戏模组注入'
    toolbox_tool_game_mod_description: str = '注入画廊解锁、修改器等通用模组'

    # 终极结构导出
    ma_suite_title: str = "翻译套件（结构优化版）"
    ma_suite_description: str = "将游戏源码提取为 Excel，并生成结构化翻译文件（translate_names/others.rpy + replace.rpy）。"
    ma_suite_game_path: str = "游戏路径:"
    ma_suite_game_path_placeholder: str = "选择游戏目录（包含 game 的上级）或 exe"
    ma_suite_select_folder: str = "选目录"
    ma_suite_select_exe: str = "选 exe"
    ma_suite_language_name: str = "语言名称:"
    ma_suite_language_name_tooltip: str = "tl/<language> 目录名，例如 chinese / schinese / tchinese"
    ma_suite_run_official_extraction_first: str = "先执行官方提取（默认关闭）"
    ma_suite_extraction_mode: str = "提取模式:"
    ma_suite_mode_standard: str = "仅标准模式（稳）"
    ma_suite_mode_external: str = "标准 + 外部文件（.json/.yml）"
    ma_suite_mode_aggressive: str = "标准 + 外部 + 强力模式（慎用）"
    ma_suite_mode_tooltip: str = "对应套件模式：1=标准，2=外部文件，3=外部文件 + 强力扫描"
    ma_suite_generate_emoji_mapping: str = "生成 Emoji 替换表"
    ma_suite_generate_emoji_mapping_tooltip: str = "扫描 tl/<lang> 中的特效标记（{} / []），生成译前/译后替换表"
    ma_suite_official_exe_optional: str = "官方提取 exe（可选）:"
    ma_suite_official_exe_placeholder: str = "仅勾选官方提取时需要，留空自动查找"
    ma_suite_generate_structure: str = "生成终极结构"
    ma_suite_emoji_helper: str = "Emoji 替换助手（目录批量）"
    ma_suite_emoji_helper_description: str = "根据映射表，对选定目录下所有 .rpy 文件执行译前或译后替换。"
    ma_suite_target_folder: str = "目标目录:"
    ma_suite_target_folder_placeholder: str = "选择需要处理的目录（如 game/tl/Chinese）"
    ma_suite_prepare_folder: str = "译前保护替换（目录）"
    ma_suite_restore_folder: str = "译后还原（目录）"
    ma_suite_select_rpy_folder: str = "选择需要处理的目录（含 .rpy）"
    ma_suite_select_game_folder: str = "选择游戏目录"
    ma_suite_select_game_executable: str = "选择游戏可执行文件"
    ma_suite_select_official_exe: str = "选择官方提取用的 exe"
    ma_suite_executable_filter: str = "可执行文件 (*.exe *.py);;所有文件 (*)"
    ma_suite_select_game_path_first: str = "请先选择游戏目录或 exe"
    ma_suite_generating_structure: str = "正在生成终极结构..."
    ma_suite_no_result_check_paths: str = "未生成任何结果，请检查路径或 tl 目录"
    ma_suite_no_result: str = "未生成结果"
    ma_suite_emoji_mapping_summary: str = "\nEmoji/Tag 对照: {emoji_count} 条 -> {emoji_dir}"
    ma_suite_result_summary: str = "角色名 {names_count} 条，其他 {others_count} 条，替换 {replace_count} 条"
    ma_suite_deleted_summary: str = "；删除 {deleted_count} 条"
    ma_suite_output_summary: str = "{summary}\n输出目录: {output}{extra}"
    ma_suite_complete_status: str = "完成：{output}"
    ma_suite_output_written: str = "已写入输出目录"
    ma_suite_execution_failed: str = "执行失败"
    ma_suite_select_target_folder: str = "请选择需要处理的目录"
    ma_suite_folder_does_not_exist: str = "目录不存在: {target}"
    ma_suite_folder_processed: str = "已处理目录: {target}\n成功 {success} 个文件，失败 {failed} 个\n备份: {backup_path}"
    ma_suite_select_game_path_above: str = "请先在上方选择游戏目录或 exe"
    ma_suite_game_folder_not_found: str = "未找到 game 目录: {game_folder}"
