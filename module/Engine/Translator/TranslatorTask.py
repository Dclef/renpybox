import dataclasses
import copy
import json
import itertools
import threading
import time
import traceback
from functools import lru_cache
from collections.abc import Callable

import rich
from rich import box
from rich import markup
from rich.table import Table

from base.Base import Base
from base.LogManager import LogManager
from module.Cache.CacheItem import CacheItem
from module.Config import Config
from module.Engine.Engine import Engine
from module.Engine.TaskRequester import TaskRequester
from module.Engine.Translator.TranslationTaskContext import TranslationTaskContext
from module.Localizer.Localizer import Localizer
from module.PromptBuilder import PromptBuilder
from module.Response.ResponseChecker import ResponseChecker
from module.Response.ResponseDecoder import ResponseDecoder
from module.Text.TextHelper import TextHelper
from module.TextProcessor import TextProcessor

@dataclasses.dataclass
class TranslatorTaskResult:
    """翻译任务返回结果。"""

    row_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    failed_line_count: int = 0
    fallback_line_count: int = 0
    line_count_mismatch_count: int = 0
    requested_line_count: int = 0
    error: bool = False
    error_msg: str = ""

    def as_dict(self) -> dict[str, object]:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class SingleLineTranslationOutcome:
    """单行翻译结果。"""

    dst: str = ""
    check: ResponseChecker.Error = ResponseChecker.Error.UNKNOWN
    failed: bool = False
    mismatch: bool = False
    fallback: bool = False
    input_tokens: int = 0
    output_tokens: int = 0
    response_think: str = ""
    response_result: str = ""
    decoder_method: str = ""
    glossarys: list[dict[str, str]] = dataclasses.field(default_factory = list)


class TranslatorTask(Base):

    # 自动术语表
    GLOSSARY_SAVE_LOCK: threading.Lock = threading.Lock()
    GLOSSARY_SAVE_TIME: float = time.time()
    GLOSSARY_SAVE_INTERVAL: int = 15

    RETRY_METADATA_KEY = CacheItem.TRANSLATION_RETRY_KEY
    RETRY_METADATA_SCHEMA_VERSION = 1
    RETRY_REASON_ORDER: tuple[str, ...] = (
        "INDEX_ALIGNMENT",
        "RESPONSE_FORMAT",
        "PLACEHOLDER_MISMATCH",
        "LINE_ERROR_EMPTY_LINE",
        "LINE_ERROR_KANA",
        "LINE_ERROR_HANGEUL",
        "LINE_ERROR_MIXED_LANGUAGE",
        "LINE_ERROR_SIMILARITY",
        "LINE_ERROR_DEGRADATION",
        "TRANSLATION_ERROR_MARKER",
        "INVALID_RESPONSE",
        "REQUEST_FAILURE",
    )

    def __init__(
        self,
        config: Config | TranslationTaskContext,
        platform: dict,
        local_flag: bool,
        items: list[CacheItem],
        precedings: list[CacheItem],
        *,
        runtime_config: Config | None = None,
        candidate_sink: Callable[[list[dict[str, str]]], None] | None = None,
    ) -> None:
        super().__init__()

        # 参数验证（防御性编程）
        if not isinstance(config, (Config, TranslationTaskContext)):
            raise TypeError(f"[INIT] Config/TranslationTaskContext 类型错误: {type(config)}")
        if not isinstance(platform, dict):
            raise TypeError(f"[INIT] Platform 类型错误: {type(platform)}")
        
        # 验证 platform 必需字段
        required_keys = ['api_url', 'model', 'api_format']
        missing = [k for k in required_keys if k not in platform]
        if missing:
            raise ValueError(f"[INIT] Platform 缺少必需字段: {missing}")
        
        if not items or len(items) == 0:
            raise ValueError(f"[INIT] Items 列表不能为空")

        # 每个任务都使用独立运行配置。旧 Config 调用会在边界生成临时上下文，
        # 新管线则直接复用已经持久化的不可变上下文。
        if isinstance(config, TranslationTaskContext):
            self.task_context = config
            task_config = config.to_runtime_config(runtime_config)
        else:
            task_config = copy.deepcopy(runtime_config or config)
            self.task_context = TranslationTaskContext.from_config(task_config)

        # 初始化
        self.items = items
        self.precedings = precedings
        self.processors = [TextProcessor(task_config, item) for item in items]
        self.config = task_config
        self.platform = copy.deepcopy(platform)
        self.local_flag = local_flag
        self.candidate_sink = candidate_sink
        self.prompt_builder = PromptBuilder(self.task_context)
        self.response_checker = ResponseChecker(self.config, items)

    def should_use_single_line_translation(self) -> bool:
        """判断是否启用单行翻译模式。"""
        if getattr(self.config, "single_line_translation_enable", False) != True:
            return False

        return self.platform.get("api_format") not in (Base.APIFormat.DEEPL, Base.APIFormat.DEEPLX)

    @staticmethod
    def _cancelled_result() -> dict[str, object]:
        """返回统一的取消结果；取消不应被记录为普通请求失败。"""
        return {
            "row_count": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cancelled": True,
        }

    def request_single_line(
        self,
        items: list[CacheItem],
        processors: list[TextProcessor],
        precedings: list[CacheItem],
        local_flag: bool,
        current_round: int,
        start_time: float,
    ) -> dict[str, object]:
        """单行翻译模式：每次请求只处理一行原文。"""
        if TaskRequester.is_cancel_requested():
            return self._cancelled_result()

        requester = TaskRequester(self.config, self.platform, current_round)
        stats = TranslatorTaskResult()
        updated_count = 0

        all_srcs: list[str] = []
        all_dsts: list[str] = []
        all_checks: list[str] = []
        file_log: list[str] = []
        console_log: list[str] = []
        all_glossarys: list[dict[str, str]] = []
        pending_updates: list[tuple[CacheItem, TextProcessor, list[str]]] = []

        # 先逐条请求，再统一写回，避免中途更新导致日志和缓存状态不一致。
        for item, processor in zip(items, processors):
            if TaskRequester.is_cancel_requested():
                return self._cancelled_result()

            item_srcs = list(processor.srcs)
            item_dsts: list[str] = []
            item_checks: list[str] = []

            if len(item_srcs) == 0:
                pending_updates.append((item, processor, []))
                continue

            for line_index, src in enumerate(item_srcs):
                if TaskRequester.is_cancel_requested():
                    return self._cancelled_result()

                outcome, extra_log = self.request_single_line_line(
                    requester = requester,
                    item = item,
                    src = src,
                    samples = processor.samples,
                    precedings = precedings,
                    local_flag = local_flag,
                )

                if TaskRequester.is_cancel_requested():
                    return self._cancelled_result()

                if line_index == 0:
                    file_log.extend(extra_log)
                    console_log.extend(extra_log)

                stats.input_tokens = stats.input_tokens + outcome.input_tokens
                stats.output_tokens = stats.output_tokens + outcome.output_tokens
                if outcome.failed:
                    stats.failed_line_count = stats.failed_line_count + 1
                if outcome.fallback:
                    stats.fallback_line_count = stats.fallback_line_count + 1
                if outcome.mismatch:
                    stats.line_count_mismatch_count = stats.line_count_mismatch_count + 1
                if outcome.glossarys != []:
                    all_glossarys.extend(outcome.glossarys)

                item_dsts.append(outcome.dst)
                item_checks.append(outcome.check)
                all_srcs.append(src)
                all_dsts.append(outcome.dst)
                all_checks.append(outcome.check)

                if outcome.response_think != "":
                    file_log.append(Localizer.get().translator_task_response_think + outcome.response_think)
                    if LogManager.get().is_expert_mode():
                        console_log.append(Localizer.get().translator_task_response_think + outcome.response_think)

                if outcome.response_result != "":
                    if LogManager.get().is_expert_mode() or outcome.decoder_method == "PLAIN_TEXT" or outcome.check != ResponseChecker.Error.NONE:
                        file_log.append(Localizer.get().translator_task_response_result + outcome.response_result)
                        if LogManager.get().is_expert_mode():
                            console_log.append(Localizer.get().translator_task_response_result + outcome.response_result)

            if TaskRequester.is_cancel_requested():
                return self._cancelled_result()

            if all(v == ResponseChecker.Error.NONE for v in item_checks):
                pending_updates.append((item, processor, item_dsts.copy()))
            else:
                self.record_failed_item_retry(
                    item,
                    item_checks,
                    item_dsts,
                    srcs = item_srcs,
                )

        if TaskRequester.is_cancel_requested():
            return self._cancelled_result()

        log_srcs, log_dsts = self.build_log_lines(processors, all_srcs, all_dsts)

        for item, processor, item_dsts in pending_updates:
            if TaskRequester.is_cancel_requested():
                return self._cancelled_result()

            name, dst = processor.post_process(item_dsts.copy())
            item.set_dst(dst)
            if name is not None:
                item.set_first_name_dst(name)
            item.set_status(Base.TranslationStatus.TRANSLATED)
            self.clear_retry_metadata(item)
            updated_count = updated_count + 1

        if updated_count > 0 and all_glossarys != []:
            with __class__.GLOSSARY_SAVE_LOCK:
                __class__.GLOSSARY_SAVE_TIME = self.merge_glossary(all_glossarys, __class__.GLOSSARY_SAVE_TIME)

        summary = Localizer.get().translator_single_line_mode_summary
        summary = summary.replace("{REQUESTED}", str(len(all_srcs)))
        summary = summary.replace("{FALLBACK}", str(stats.fallback_line_count))
        summary = summary.replace("{FAILED}", str(stats.failed_line_count))
        summary = summary.replace("{MISMATCH}", str(stats.line_count_mismatch_count))
        file_log.insert(0, summary)
        console_log.insert(0, summary)

        self.print_log_table(
            all_checks,
            start_time,
            stats.input_tokens,
            stats.output_tokens,
            log_srcs,
            log_dsts,
            file_log,
            console_log,
        )

        stats.row_count = updated_count
        stats.requested_line_count = len(all_srcs)
        return stats.as_dict()

    def request_single_line_line(
        self,
        requester: TaskRequester,
        item: CacheItem,
        src: str,
        samples: list[str],
        precedings: list[CacheItem],
        local_flag: bool,
    ) -> tuple[SingleLineTranslationOutcome, list[str]]:
        """执行单行请求、解析和校验。"""
        if TaskRequester.is_cancel_requested():
            return SingleLineTranslationOutcome(
                check = ResponseChecker.Error.UNKNOWN,
                failed = True,
                mismatch = True,
            ), []

        messages, extra_log = self.prompt_builder.generate_single_line_prompt(
            src = src,
            samples = samples,
            precedings = precedings,
            local_flag = local_flag,
            item = item,
        )

        skip, response_think, response_result, input_tokens, output_tokens = requester.request(
            messages,
            response_shape = "none",
        )
        response_think = response_think or ""
        response_result = response_result or ""
        input_tokens = int(input_tokens or 0)
        output_tokens = int(output_tokens or 0)

        if TaskRequester.is_cancel_requested():
            return SingleLineTranslationOutcome(
                check = ResponseChecker.Error.UNKNOWN,
                failed = True,
                mismatch = True,
                input_tokens = input_tokens,
                output_tokens = output_tokens,
                response_think = response_think,
                response_result = response_result,
            ), extra_log

        if skip == True or response_result.strip() == "":
            return SingleLineTranslationOutcome(
                check = ResponseChecker.Error.UNKNOWN,
                failed = True,
                mismatch = True,
                input_tokens = input_tokens,
                output_tokens = output_tokens,
                response_think = response_think,
                response_result = response_result,
            ), extra_log

        decoder = ResponseDecoder()
        decode_result = decoder.decode_result(response_result, 1, allow_plain_text_single = True)
        if decode_result.glossarys != []:
            glossarys = decode_result.glossarys.copy()
        else:
            glossarys = []

        if len(decode_result.dsts) != 1:
            return SingleLineTranslationOutcome(
                check = ResponseChecker.Error.FAIL_DATA,
                failed = True,
                mismatch = True,
                input_tokens = input_tokens,
                output_tokens = output_tokens,
                response_think = response_think,
                response_result = response_result,
                decoder_method = decode_result.method,
                glossarys = glossarys,
            ), extra_log

        dst = decode_result.dsts[0]
        check = ResponseChecker(self.config, [item]).check([src], [dst], item.get_text_type())[0]
        return SingleLineTranslationOutcome(
            dst = dst,
            check = check,
            failed = check != ResponseChecker.Error.NONE,
            mismatch = False,
            fallback = decode_result.method == "PLAIN_TEXT",
            input_tokens = input_tokens,
            output_tokens = output_tokens,
            response_think = response_think,
            response_result = response_result,
            decoder_method = decode_result.method,
            glossarys = glossarys,
        ), extra_log

    # 启动任务
    def start(self, current_round: int) -> dict[str, object]:
        """
        启动翻译任务，包含异常捕获确保线程不会静默死亡
        """
        self.info(f"[TASK-START] 任务启动: items={len(self.items)}, round={current_round+1}, "
                  f"model={self.platform.get('model', 'unknown')}")
        try:
            return self.request(self.items, self.processors, self.precedings, self.local_flag, current_round)
        except Exception as e:
            # 关键：捕获所有异常，防止线程静默死亡导致主流程挂起
            error_msg = f"任务执行失败: {str(e)}"
            self.error(f"[TASK-CRASH] {error_msg}")
            self.error(f"[TASK-CRASH] 完整堆栈:\n{traceback.format_exc()}")
            
            # 确保返回有效结果，防止主线程无限等待
            return TranslatorTaskResult(error = True, error_msg = error_msg).as_dict()

    # 请求
    def request(self, items: list[CacheItem], processors: list[TextProcessor], precedings: list[CacheItem], local_flag: bool, current_round: int) -> dict[str, object]:
        if TaskRequester.is_cancel_requested():
            return self._cancelled_result()

        # 任务开始的时间
        start_time = time.time()
        
        # 添加请求入口日志
        self.debug(f"[REQUEST-START] 开始处理: items={len(items)}, precedings={len(precedings)}, local={local_flag}")

        # 文本预处理
        srcs: list[str] = []
        line_items: list[CacheItem] = []
        samples: list[str] = []
        for item, processor in zip(items, processors):
            if TaskRequester.is_cancel_requested():
                return self._cancelled_result()

            processor.pre_process()

            # 获取预处理后的数据
            srcs.extend(processor.srcs)
            line_items.extend([item] * len(processor.srcs))
            samples.extend(processor.samples)

        # 如果没有任何有效原文文本，则直接完成当前任务
        if len(srcs) == 0:
            if TaskRequester.is_cancel_requested():
                return self._cancelled_result()

            self.debug(f"[REQUEST] 无有效原文，直接标记完成")
            for item, processor in zip(items, processors):
                item.set_dst(item.get_src())
                item.set_status(Base.TranslationStatus.TRANSLATED)
                self.clear_retry_metadata(item)

            return {
                "row_count": len(items),
                "input_tokens": 0,
                "output_tokens": 0,
            }

        # 单行模式直接转入逐行请求流程，避免批量 JSONLINE 格式对齐失败。
        if self.should_use_single_line_translation():
            if TaskRequester.is_cancel_requested():
                return self._cancelled_result()

            self.debug(f"[REQUEST] 启用单行翻译模式")
            return self.request_single_line(
                items,
                processors,
                precedings,
                local_flag,
                current_round,
                start_time,
            )

        # 生成请求提示词
        if TaskRequester.is_cancel_requested():
            return self._cancelled_result()

        self.debug(f"[REQUEST] 生成提示词: srcs={len(srcs)}, api_format={self.platform.get('api_format')}")
        if self.platform.get("api_format") != Base.APIFormat.SAKURALLM:
            self.messages, console_log = self.prompt_builder.generate_prompt(
                srcs,
                samples,
                precedings,
                local_flag,
                items = self.items,
            )
        else:
            self.messages, console_log = self.prompt_builder.generate_prompt_sakura(
                srcs,
                items = self.items,
            )
        
        # 验证消息是否生成成功
        if not isinstance(self.messages, list) or len(self.messages) == 0:
            self.error(f"[REQUEST] 消息构建失败: type={type(self.messages)}, "
                      f"len={len(self.messages) if isinstance(self.messages, list) else 'N/A'}")
            return {
                "row_count": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "error": True,
                "error_msg": "消息构建失败",
            }
        
        self.debug(f"[REQUEST] 提示词生成完成: messages={len(self.messages)}")

        if TaskRequester.is_cancel_requested():
            return self._cancelled_result()

        # 发起请求
        requester = TaskRequester(self.config, self.platform, current_round)
        structured_response = (
            self.config.structured_output_enable
            and self.platform.get("api_format")
            not in (Base.APIFormat.SAKURALLM, Base.APIFormat.DEEPL, Base.APIFormat.DEEPLX)
        )
        self.debug(f"[REQUEST] 发起API请求...")
        skip, response_think, response_result, input_tokens, output_tokens = requester.request(
            self.messages,
            response_shape = "json_object" if structured_response else "none",
        )

        if TaskRequester.is_cancel_requested():
            return self._cancelled_result()

        # 如果请求结果标记为 skip，即有错误发生，则跳过本次循环
        if skip == True:
            self.warning(f"[REQUEST] API请求被跳过（发生错误）")
            self.record_failed_item_retries(
                items,
                processors,
                [ResponseChecker.Error.UNKNOWN] * len(srcs),
                [""] * len(srcs),
                retry_reason_code = "REQUEST_FAILURE",
            )
            return {
                "row_count": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "failed_line_count": len(srcs),
                "requested_line_count": len(srcs),
            }
        
        self.debug(f"[REQUEST] API请求完成: input_tokens={input_tokens}, output_tokens={output_tokens}, "
                   f"response_len={len(response_result) if response_result else 0}")

        # 内容被安全审查阻止时，Gemini 可能返回空内容；TaskRequester 会用特殊 JSON 标记。
        # 这种情况属于不可重试错误：对单条目任务直接标记为 EXCLUDED，避免无限重试；
        # 对多条目任务则拆分成单条目尝试，尽量保留可翻译的部分。
        if isinstance(response_result, str) and '"blocked"' in response_result:
            try:
                marker = json.loads(response_result)
            except Exception:
                marker = None

            if isinstance(marker, dict) and marker.get("blocked") is True:
                if TaskRequester.is_cancel_requested():
                    return self._cancelled_result()
                if len(items) == 1:
                    item = items[0]
                    if item.get_status() == Base.TranslationStatus.UNTRANSLATED:
                        item.set_status(Base.TranslationStatus.EXCLUDED)
                        item.set_dst("")
                    self.clear_retry_metadata(item)
                    src_preview = (item.get_src() or "").replace("\n", " ").strip()
                    if len(src_preview) > 120:
                        src_preview = src_preview[:120] + "…"
                    self.warning(f"Content blocked by safety filter, skipped 1 line: {src_preview}")
                    return {
                        "row_count": 1,
                        "input_tokens": 0,
                        "output_tokens": 0,
                    }

                self.warning(f"Content blocked by safety filter, splitting batch: {len(items)} lines")
                total_row_count = 0
                total_input_tokens = 0
                total_output_tokens = 0
                total_failed_line_count = 0
                total_fallback_line_count = 0
                total_line_count_mismatch_count = 0
                total_requested_line_count = 0
                for item in items:
                    if TaskRequester.is_cancel_requested():
                        break
                    result = self.request([item], [TextProcessor(self.config, item)], precedings, local_flag, current_round)
                    total_row_count += int(result.get("row_count", 0) or 0)
                    total_input_tokens += int(result.get("input_tokens", 0) or 0)
                    total_output_tokens += int(result.get("output_tokens", 0) or 0)
                    total_failed_line_count += int(result.get("failed_line_count", 0) or 0)
                    total_fallback_line_count += int(result.get("fallback_line_count", 0) or 0)
                    total_line_count_mismatch_count += int(result.get("line_count_mismatch_count", 0) or 0)
                    total_requested_line_count += int(result.get("requested_line_count", 0) or 0)
                return {
                    "row_count": total_row_count,
                    "input_tokens": total_input_tokens,
                    "output_tokens": total_output_tokens,
                    "failed_line_count": total_failed_line_count,
                    "fallback_line_count": total_fallback_line_count,
                    "line_count_mismatch_count": total_line_count_mismatch_count,
                    "requested_line_count": total_requested_line_count,
                }

        if TaskRequester.is_cancel_requested():
            return self._cancelled_result()

        # 解析并按 request_index 对齐。严格协议失败时返回空记录，整批进入重试。
        decode_result = ResponseDecoder().decode_result(
            response_result,
            expected_count = len(srcs),
            structured = structured_response,
        )
        dsts = decode_result.dsts
        glossarys = decode_result.glossarys

        # Sakura JSONLINE 解析失败时尝试格式化重试（结构化模式下跳过）
        if (
            not structured_response
            and self.platform.get("api_format") == Base.APIFormat.SAKURALLM
            and self.config.sakura_jsonline_retry_enable == True
            and (len(dsts) == 0 or all(v == "" or v == None for v in dsts))
        ):
            console_log.append("Sakura 回复未按 JSONLINE 输出，尝试格式化重试。")
            retry_messages, retry_log = self.prompt_builder.generate_prompt_sakura_format_retry(srcs, response_result)
            if retry_log:
                console_log.extend(retry_log)
            if TaskRequester.is_cancel_requested():
                return self._cancelled_result()
            retry_skip, retry_think, retry_result, retry_input_tokens, retry_output_tokens = requester.request(
                retry_messages,
                response_shape = "none",
            )
            if TaskRequester.is_cancel_requested():
                return self._cancelled_result()
            if retry_skip == False and isinstance(retry_result, str):
                retry_decode_result = ResponseDecoder().decode_result(
                    retry_result,
                    expected_count = len(srcs),
                )
                if retry_decode_result.translations != ():
                    decode_result = retry_decode_result
                    dsts = retry_decode_result.dsts
                    glossarys = retry_decode_result.glossarys
                    response_result = retry_result
                    if retry_think != "":
                        response_think = (response_think + "\n" + retry_think) if response_think != "" else retry_think
                    input_tokens = (input_tokens or 0) + (retry_input_tokens or 0)
                    output_tokens = (output_tokens or 0) + (retry_output_tokens or 0)

        # 严格协议解析失败时不能进入内容检查。解码器只会返回完整、已按
        # request_index 对齐的结果，因此空 translations 表示整个批次协议失败。
        if TaskRequester.is_cancel_requested():
            return self._cancelled_result()

        decode_retry_reason: str | None = None
        if decode_result.translations == ():
            checks = [ResponseChecker.Error.FAIL_DATA] * len(srcs)
            decode_retry_reason = "INDEX_ALIGNMENT"
        else:
            # TODO - 当前逻辑下任务不会跨文件，所以一个任务的 TextType 都是一样的，有效，但是十分的 UGLY
            checks = self.response_checker.check(
                srcs,
                dsts,
                self.items[0].get_text_type(),
                line_items = line_items,
            )

        # 记录失败条目的重试次数；明确的翻译失败标记达到阈值后排除，避免反复重试到最大轮次。
        if TaskRequester.is_cancel_requested():
            return self._cancelled_result()
        self.record_failed_item_retries(
            items,
            processors,
            checks,
            dsts,
            retry_reason_code = decode_retry_reason,
        )

        # 模型回复日志
        # 在这里将日志分成打印在控制台和写入文件的两份，按不同逻辑处理
        file_log = console_log.copy()
        if response_think != "":
            file_log.append(Localizer.get().translator_task_response_think + response_think)
            console_log.append(Localizer.get().translator_task_response_think + response_think)
        if response_result != "":
            file_log.append(Localizer.get().translator_task_response_result + response_result)
            console_log.append(Localizer.get().translator_task_response_result + response_result) if LogManager.get().is_expert_mode() else None

        # 日志展示使用恢复后的文本，避免保护占位符影响排查。
        log_srcs, log_dsts = self.build_log_lines(processors, srcs, dsts)

        # 如果有任何正确的条目，则处理结果
        updated_count = 0
        if (
            len(dsts) == len(srcs)
            and len(checks) == len(srcs)
            and any(v == ResponseChecker.Error.NONE for v in checks)
        ):
            if TaskRequester.is_cancel_requested():
                return self._cancelled_result()
            # 更新术语表
            with __class__.GLOSSARY_SAVE_LOCK:
                __class__.GLOSSARY_SAVE_TIME = self.merge_glossary(glossarys, __class__.GLOSSARY_SAVE_TIME)

            # 更新缓存数据
            dsts_cp = dsts.copy()
            checks_cp = checks.copy()
            for item, processor in zip(items, processors):
                length = len(processor.srcs)
                dsts_ex = [dsts_cp.pop(0) for _ in range(length)]
                checks_ex = [checks_cp.pop(0) for _ in range(length)]

                if all(v == ResponseChecker.Error.NONE for v in checks_ex):
                    name, dst = processor.post_process(dsts_ex)
                    item.set_dst(dst)
                    item.set_first_name_dst(name) if name is not None else None
                    item.set_status(Base.TranslationStatus.TRANSLATED)
                    self.clear_retry_metadata(item)
                    updated_count = updated_count + 1

        # 打印任务结果
        self.print_log_table(
            checks,
            start_time,
            input_tokens,
            output_tokens,
            log_srcs,
            log_dsts,
            file_log,
            console_log
        )

        # 返回任务结果
        if updated_count > 0:
            return {
                "row_count": updated_count,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "failed_line_count": sum(1 for v in checks if v != ResponseChecker.Error.NONE),
                "line_count_mismatch_count": sum(1 for v in checks if v == ResponseChecker.Error.FAIL_LINE_COUNT),
                "requested_line_count": len(srcs),
            }
        else:
            return {
                "row_count": 0,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "failed_line_count": sum(1 for v in checks if v != ResponseChecker.Error.NONE),
                "line_count_mismatch_count": sum(1 for v in checks if v == ResponseChecker.Error.FAIL_LINE_COUNT),
                "requested_line_count": len(srcs),
            }

    def record_failed_item_retries(
        self,
        items: list[CacheItem],
        processors: list[TextProcessor],
        checks: list[ResponseChecker.Error],
        dsts: list[str],
        *,
        retry_reason_code: str | None = None,
    ) -> None:
        total_length = sum(len(processor.srcs) for processor in processors)

        # 不补齐模型结果。任何内部长度不一致都作为索引对齐失败记录，且
        # 后续写回条件会拒绝这批数据。
        if len(checks) != total_length or len(dsts) != total_length:
            for item, processor in zip(items, processors):
                length = len(processor.srcs)
                if length == 0:
                    continue
                self.record_failed_item_retry(
                    item,
                    [ResponseChecker.Error.FAIL_LINE_COUNT] * length,
                    [],
                    srcs = list(processor.srcs),
                    retry_reason_code = retry_reason_code or "INDEX_ALIGNMENT",
                )
            return

        offset = 0
        for item, processor in zip(items, processors):
            length = len(processor.srcs)
            if length == 0:
                continue
            item_checks = checks[offset:offset + length]
            item_dsts = dsts[offset:offset + length]
            self.record_failed_item_retry(
                item,
                item_checks,
                item_dsts,
                srcs = list(processor.srcs),
                retry_reason_code = retry_reason_code,
            )
            offset += length

    def record_failed_item_retry(
        self,
        item: CacheItem,
        checks: list[ResponseChecker.Error],
        dsts: list[str],
        *,
        srcs: list[str] | None = None,
        retry_reason_code: str | None = None,
    ) -> None:
        if checks == [] or all(v == ResponseChecker.Error.NONE for v in checks):
            return

        retry_count = item.get_retry_count() + 1
        item.set_retry_count(retry_count)
        self.set_retry_metadata(
            item,
            checks,
            srcs or [],
            dsts,
            retry_count,
            retry_reason_code = retry_reason_code,
        )

        if self.should_exclude_terminal_translation_error(checks, dsts, retry_count):
            item.set_dst("")
            item.set_status(Base.TranslationStatus.EXCLUDED)
            preview = (item.get_src() or "").replace("\n", " ").strip()
            if len(preview) > 120:
                preview = preview[:120] + "…"
            self.warning(f"[REQUEST] 翻译失败标记已达到重试阈值，已排除: {preview}")

    @classmethod
    def clear_retry_metadata(cls, item: CacheItem) -> None:
        metadata = item.get_metadata()
        if cls.RETRY_METADATA_KEY not in metadata:
            return
        metadata.pop(cls.RETRY_METADATA_KEY, None)
        item.set_metadata(metadata)

    @classmethod
    def set_retry_metadata(
        cls,
        item: CacheItem,
        checks: list[ResponseChecker.Error],
        srcs: list[str],
        dsts: list[str],
        retry_count: int,
        *,
        retry_reason_code: str | None = None,
    ) -> None:
        grouped: dict[str, list[int]] = {}
        for line_index, check in enumerate(checks):
            if check == ResponseChecker.Error.NONE:
                continue
            src = srcs[line_index] if line_index < len(srcs) else ""
            dst = dsts[line_index] if line_index < len(dsts) else ""
            code = retry_reason_code or cls.classify_retry_reason(check, src, dst)
            grouped.setdefault(code, []).append(line_index)

        if grouped == {}:
            return

        ordered_codes = [code for code in cls.RETRY_REASON_ORDER if code in grouped]
        ordered_codes.extend(sorted(code for code in grouped if code not in cls.RETRY_REASON_ORDER))
        reasons = [
            {
                "code": code,
                "line_indices": sorted(set(grouped[code])),
            }
            for code in ordered_codes
        ]

        metadata = item.get_metadata()
        metadata[cls.RETRY_METADATA_KEY] = {
            "schema_version": cls.RETRY_METADATA_SCHEMA_VERSION,
            "attempt": max(0, int(retry_count)),
            "reasons": reasons,
        }
        item.set_metadata(metadata)

    @classmethod
    def classify_retry_reason(
        cls,
        check: ResponseChecker.Error,
        src: str,
        dst: str,
    ) -> str:
        if check == ResponseChecker.Error.FAIL_LINE_COUNT:
            return "INDEX_ALIGNMENT"
        if check == ResponseChecker.Error.FAIL_DATA:
            if (src or "").strip() != "" and (dst or "").strip() == "":
                return "LINE_ERROR_EMPTY_LINE"
            return "RESPONSE_FORMAT"
        if check == ResponseChecker.Error.UNKNOWN:
            return "REQUEST_FAILURE"
        if check == ResponseChecker.Error.LINE_ERROR_FAKE_REPLY:
            if ResponseChecker.has_translation_error_marker(dst):
                return "TRANSLATION_ERROR_MARKER"
            src_tokens = sorted(ResponseChecker.RE_PRESERVE_TOKEN.findall(src or ""))
            dst_tokens = sorted(ResponseChecker.RE_PRESERVE_TOKEN.findall(dst or ""))
            if src_tokens != dst_tokens:
                return "PLACEHOLDER_MISMATCH"
            return "INVALID_RESPONSE"
        return str(check)

    @classmethod
    def should_exclude_terminal_translation_error(
        cls,
        checks: list[ResponseChecker.Error],
        dsts: list[str],
        retry_count: int,
    ) -> bool:
        if retry_count < ResponseChecker.RETRY_COUNT_THRESHOLD:
            return False
        if checks == []:
            return False
        if all(v == ResponseChecker.Error.LINE_ERROR_FAKE_REPLY for v in checks) == False:
            return False
        return all(ResponseChecker.has_translation_error_marker(dst) for dst in dsts)

    def build_log_lines(self, processors: list[TextProcessor], srcs: list[str], dsts: list[str]) -> tuple[list[str], list[str]]:
        """构造日志展示文本，尽量还原保护占位符后的可读内容。"""
        log_srcs: list[str] = []
        log_dsts: list[str] = []
        offset = 0

        for processor in processors:
            length = len(processor.srcs)
            src_slice = srcs[offset:offset + length]
            dst_slice = dsts[offset:offset + length]

            log_srcs.extend(processor.restore_lines_for_log(src_slice))
            log_dsts.extend(processor.restore_lines_for_log(dst_slice))
            offset += length

        if offset < len(srcs):
            log_srcs.extend([
                line.strip() if isinstance(line, str) else ""
                for line in srcs[offset:]
            ])
        if offset < len(dsts):
            log_dsts.extend([
                line.strip() if isinstance(line, str) else ""
                for line in dsts[offset:]
            ])

        return log_srcs, log_dsts

    # 合并术语表
    def merge_glossary(self, glossary_list: list[dict[str, str]], last_save_time: float) -> float:
        # 运行时发现的术语只能进入项目候选区，不能修改当前任务快照或全局配置。
        if getattr(self.config, "auto_glossary_enable", False) is not True:
            return last_save_time
        if self.candidate_sink is None:
            return last_save_time

        # 合并去重后的术语表
        candidates: list[dict[str, str]] = []
        keys: set[tuple[str, str]] = set()
        for item in glossary_list:
            if not isinstance(item, dict):
                continue
            src = str(item.get("source", item.get("src", "")) or "").strip()
            dst = str(item.get("target", item.get("dst", "")) or "").strip()
            info = str(item.get("note", item.get("info", "")) or "").strip()

            # 将原文和译文都按标点切分
            srcs: list[str] = TextHelper.split_by_punctuation(src, split_by_space = True)
            dsts: list[str] = TextHelper.split_by_punctuation(dst, split_by_space = True)
            if len(srcs) != len(dsts):
                srcs = [src]
                dsts = [dst]

            for src, dst in zip(srcs, dsts):
                src = src.strip()
                dst = dst.strip()
                if src == dst or src == "" or dst == "":
                    continue
                key = (src.casefold(), dst.casefold())
                if key not in keys:
                    keys.add(key)
                    candidates.append({
                        "source": src,
                        "target": dst,
                        "note": info,
                    })

        if candidates:
            self.candidate_sink(candidates)
            return time.time()

        return last_save_time

    # 打印日志表格
    def print_log_table(self, checks: list[str], start: int, pt: int, ct: int, srcs: list[str], dsts: list[str], file_log: list[str], console_log: list[str]) -> None:
        # 停止任务时跳过复杂日志输出，避免停止后界面卡顿
        if TaskRequester.is_cancel_requested():
            return

        # 拼接错误原因文本
        reason: str = ""
        if any(v != ResponseChecker.Error.NONE for v in checks):
            error_texts = {
                __class__.get_error_text(v) for v in checks
                if v != ResponseChecker.Error.NONE
            }
            reason = f"（{'、'.join(error_texts)}）"

        failed_count = sum(1 for v in checks if v != ResponseChecker.Error.NONE)
        line_stats = ""
        if failed_count > 0:
            line_stats = (
                "（"
                + Localizer.get().translator_response_check_fail_line_stats.replace("{FAILED}", str(failed_count)).replace("{TOTAL}", str(len(srcs)))
                + "）"
            )

        if all(v == ResponseChecker.Error.UNKNOWN for v in checks):
            style = "red"
            message = f"{Localizer.get().translator_response_check_fail} {reason}{line_stats}"
            log_func = self.error
        elif all(v == ResponseChecker.Error.FAIL_DATA for v in checks):
            style = "red"
            message = f"{Localizer.get().translator_response_check_fail} {reason}{line_stats}"
            log_func = self.error
        elif all(v == ResponseChecker.Error.FAIL_LINE_COUNT for v in checks):
            style = "red"
            message = f"{Localizer.get().translator_response_check_fail} {reason}{line_stats}"
            log_func = self.error
        elif all(v in ResponseChecker.LINE_ERROR for v in checks):
            style = "red"
            message = f"{Localizer.get().translator_response_check_fail_all} {reason}{line_stats}"
            log_func = self.error
        elif any(v in ResponseChecker.LINE_ERROR for v in checks):
            style = "yellow"
            message = f"{Localizer.get().translator_response_check_fail_part} {reason}{line_stats}"
            log_func = self.warning
        else:
            style = "green"
            message = Localizer.get().translator_task_success.replace("{TIME}", f"{(time.time() - start):.2f}")
            message = message.replace("{LINES}", f"{len(srcs)}")
            message = message.replace("{PT}", f"{pt}")
            message = message.replace("{CT}", f"{ct}")
            log_func = self.info

        # 添加日志
        file_log.insert(0, message)
        console_log.insert(0, message)

        # 写入日志到文件
        file_rows = self.generate_log_rows(srcs, dsts, file_log, console = False)
        log_func("\n" + "\n\n".join(file_rows) + "\n", file = True, console = False)

        # 根据线程数判断是否需要打印表格
        if Engine.get().get_running_task_count() > 32:
            rich.get_console().print(
                Localizer.get().translator_too_many_task + "\n" + message + "\n"
            )
        else:
            rich.get_console().print(
                self.generate_log_table(
                    self.generate_log_rows(srcs, dsts, console_log, console = True),
                    style,
                )
            )

    # 生成日志行
    def generate_log_rows(self, srcs: list[str], dsts: list[str], extra: list[str], console: bool) -> tuple[list[str], str]:
        rows = []

        # 添加额外日志
        for v in extra:
            rows.append(markup.escape(v.strip()))

        # 原文译文对比
        pair = ""
        for src, dst in itertools.zip_longest(srcs, dsts, fillvalue = ""):
            if console == False:
                pair = pair + "\n" + f"{src} --> {dst}"
            else:
                pair = pair + "\n" + f"{markup.escape(src)} [bright_blue]-->[/] {markup.escape(dst)}"
        rows.append(pair.strip())

        return rows

    # 生成日志表格
    def generate_log_table(self, rows: list, style: str) -> Table:
        table = Table(
            box = box.ASCII2,
            expand = True,
            title = " ",
            caption = " ",
            highlight = True,
            show_lines = True,
            show_header = False,
            show_footer = False,
            collapse_padding = True,
            border_style = style,
        )
        table.add_column("", style = "white", ratio = 1, overflow = "fold")

        for row in rows:
            if isinstance(row, str):
                table.add_row(row)
            else:
                table.add_row(*row)

        return table

    @classmethod
    @lru_cache(maxsize = None)
    def get_error_text(cls, error: ResponseChecker.Error) -> str:
        if error == ResponseChecker.Error.FAIL_DATA:
            return Localizer.get().response_checker_fail_data
        elif error == ResponseChecker.Error.FAIL_LINE_COUNT:
            return Localizer.get().response_checker_fail_line_count
        elif error == ResponseChecker.Error.LINE_ERROR_KANA:
            return Localizer.get().response_checker_line_error_kana
        elif error == ResponseChecker.Error.LINE_ERROR_HANGEUL:
            return Localizer.get().response_checker_line_error_hangeul
        elif error == ResponseChecker.Error.LINE_ERROR_FAKE_REPLY:
            return Localizer.get().response_checker_line_error_fake_reply
        elif error == ResponseChecker.Error.LINE_ERROR_EMPTY_LINE:
            return Localizer.get().response_checker_line_error_empty_line
        elif error == ResponseChecker.Error.LINE_ERROR_MIXED_LANGUAGE:
            return Localizer.get().response_checker_line_error_mixed_language
        elif error == ResponseChecker.Error.LINE_ERROR_SIMILARITY:
            return Localizer.get().response_checker_line_error_similarity
        elif error == ResponseChecker.Error.LINE_ERROR_DEGRADATION:
            return Localizer.get().response_checker_line_error_degradation
        else:
            return Localizer.get().response_checker_unknown
