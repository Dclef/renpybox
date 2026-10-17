"""一条龙流水线：检测、解包、反编译、抽取、翻译、回填、兜底。

无界面、不依赖 api 或 Agent。启停翻译、解包等动作由调用方注入。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from base.LogManager import LogManager
from module.Engine.Engine import Engine
from module.Localizer.Localizer import Localizer
from module.OneKey.flow import (
    detect_game_status,
    read_translation_cache_progress,
    resolve_extraction_incremental,
    resolve_translation_apply_paths,
)
from module.Renpy.ProjectPaths import RenpyProjectPaths


STAGE_DETECT = "detect"
STAGE_UNPACK = "unpack"
STAGE_DECOMPILE = "decompile"
STAGE_EXTRACT = "extract"
STAGE_TRANSLATE = "translate"
STAGE_APPLY = "apply"
STAGE_FALLBACK = "fallback"
STAGE_DONE = "done"

PIPELINE_STAGES = (
    STAGE_DETECT,
    STAGE_UNPACK,
    STAGE_DECOMPILE,
    STAGE_EXTRACT,
    STAGE_TRANSLATE,
    STAGE_APPLY,
    STAGE_FALLBACK,
    STAGE_DONE,
)

# 翻译轮询间隔与取消后等待终态的上限。``_sleep`` 是测试注入点：
# 直接打补丁 ``time.sleep`` 会污染同进程里的其它线程。
POLL_SECONDS = 2
CANCEL_WAIT_SECONDS = 120
# 启动翻译是事件投递，``accepted`` 只代表受理；引擎要等线程领票后才离开 IDLE。
# 超过这个宽限期仍在 IDLE 且仍有待译条目，就判定启动失败而不是静默回填。
START_GRACE_SECONDS = 60
_sleep: Callable[[float], None] = time.sleep


class PipelineCallbacks(Protocol):
    """工具层注入的动作。返回值用鸭子类型，避免本模块依赖 Agent。"""

    def unpack(self, cancel_check: Callable[[], bool] | None) -> Any: ...

    def decompile(self, cancel_check: Callable[[], bool] | None) -> Any: ...

    def extract(
        self,
        incremental: bool,
        cancel_check: Callable[[], bool] | None,
        progress: Callable[[str, int, str], None],
    ) -> Any: ...

    def start_translation(self, params: dict) -> dict: ...

    def stop_translation(self) -> dict: ...

    def translation_state(self) -> dict: ...

    def apply(self, mode: str) -> Any: ...

    def fallback(self) -> Any: ...


@dataclass
class PipelineOutcome:
    success: bool
    code: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)


def pipeline_identity(config) -> dict[str, str]:
    """项目身份快照。确认时锁这四项，不把会随抽取变化的 TL 签名算进去。"""
    import os

    paths = RenpyProjectPaths.from_config(config)
    if paths is None:
        return {}

    def norm(value: object) -> str:
        return os.path.normcase(os.path.normpath(str(value or "")))

    return {
        "project_root": norm(paths.project_root),
        "game_dir": norm(paths.game_dir),
        "tl_dir": norm(paths.tl_language_dir),
        "language": norm(paths.language),
    }


def _cancelled(cancel_check: Callable[[], bool] | None) -> bool:
    if cancel_check is None:
        return False
    try:
        return bool(cancel_check())
    except Exception as exc:
        LogManager.get().error(f"流水线取消检查失败: {exc}")
        return False


def _emit_progress(progress, stage: str, percent: int, detail: str) -> None:
    if progress is None:
        return
    try:
        progress(stage, int(percent), str(detail or ""))
    except Exception as exc:
        LogManager.get().error(f"流水线进度回调失败: {stage}: {exc}")


def _engine_idle() -> bool:
    engine = Engine.get()
    return engine.get_status() == Engine.Status.IDLE and not engine.has_stop_barrier()


def _engine_starting() -> bool:
    """启动票据还在有效期内：请求已受理，但翻译线程尚未领票。"""

    engine = Engine.get()
    check = getattr(engine, "has_translation_reservation", None)
    if not callable(check):
        return False
    try:
        return bool(check())
    except Exception:
        return False


def _attr(result: Any, name: str, default: Any = "") -> Any:
    if isinstance(result, dict):
        return result.get(name, default)
    return getattr(result, name, default)


def _output_has_rpy(config) -> bool:
    from pathlib import Path

    output, _input = resolve_translation_apply_paths(config)
    if output is None:
        return False
    raw = str(output).strip()
    if not raw or raw == ".":
        return False
    folder = Path(raw)
    if not folder.is_dir():
        return False
    return any(path.is_file() and path.suffix.lower() == ".rpy" for path in folder.rglob("*.rpy"))


def _has_completed_translation(config) -> bool:
    """主缓存存在且没有待译条目，才算上一次翻译真的完成。"""

    output, _input = resolve_translation_apply_paths(config)
    if output is None:
        return False
    _progress, _status, untranslated, cache_ready = read_translation_cache_progress(
        str(output)
    )
    return bool(cache_ready) and untranslated == 0


def _percent(progress: dict) -> int:
    if not isinstance(progress, dict):
        return -1
    if "percent" in progress:
        try:
            return int(round(float(progress["percent"])))
        except (TypeError, ValueError):
            return -1
    line = progress.get("line")
    total = progress.get("total_line")
    if isinstance(line, int) and isinstance(total, int) and total > 0:
        return int(round(min(100.0, line / total * 100.0)))
    return -1


def _translate_detail(progress: dict) -> str:
    if not isinstance(progress, dict):
        return ""
    line = progress.get("line")
    total = progress.get("total_line")
    if not isinstance(line, int) or not isinstance(total, int):
        return ""
    return Localizer.get().agent_pipeline_translate_progress.format(
        line=line,
        total_line=total,
    )


def _wait_until_idle() -> None:
    deadline = time.monotonic() + CANCEL_WAIT_SECONDS
    while time.monotonic() < deadline:
        if _engine_idle():
            return
        _sleep(POLL_SECONDS)


def run_pipeline(
    config,
    *,
    callbacks: PipelineCallbacks,
    progress: Callable[[str, int, str], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
    incremental: str = "auto",
    auto_apply: bool = True,
    auto_fallback: bool = True,
    preflight_confirmed: bool = False,
    use_agent_model: bool = True,
) -> PipelineOutcome:
    """按固定顺序推进整盘汉化。任一步失败即停止，不继续回填。"""
    steps: list[dict[str, Any]] = []
    applied_files = 0
    fallback_count = 0
    translated_count = 0

    def finish(
        success: bool,
        code: str,
        message: str = "",
        **extra: Any,
    ) -> PipelineOutcome:
        data = {
            "steps": list(steps),
            "applied_files": applied_files,
            "fallback_count": fallback_count,
            "translated_count": translated_count,
            "tl_dir": "",
        }
        paths = RenpyProjectPaths.from_config(config)
        if paths is not None:
            data["tl_dir"] = str(paths.tl_language_dir)
        data.update(extra)
        return PipelineOutcome(success, code, message, data)

    def record(stage: str, success: bool, code: str) -> None:
        steps.append({"stage": stage, "success": success, "code": code})
        LogManager.get().info(f"一条龙阶段 {stage}: {code}")

    paths = RenpyProjectPaths.from_config(config)
    if paths is None or not paths.game_dir.is_dir():
        return finish(False, "PROJECT_NOT_SET")
    identity = pipeline_identity(config)
    if not _engine_idle():
        return finish(False, "ENGINE_BUSY")

    status = ""
    detect_message = ""
    for _round in range(3):
        if _cancelled(cancel_check):
            record(STAGE_DETECT, False, "CANCELLED")
            return finish(False, "CANCELLED")
        _emit_progress(progress, STAGE_DETECT, 0, "")
        status, detect_message = detect_game_status(
            str(paths.project_root),
            paths.language,
            cancel_check=cancel_check,
        )
        if status == "cancelled" or _cancelled(cancel_check):
            record(STAGE_DETECT, False, "CANCELLED")
            return finish(False, "CANCELLED")
        if status == "need_unpack":
            _emit_progress(progress, STAGE_UNPACK, -1, "")
            unpacked = callbacks.unpack(cancel_check)
            if _attr(unpacked, "code") == "CANCELLED" or _cancelled(cancel_check):
                record(STAGE_UNPACK, False, "CANCELLED")
                return finish(False, "CANCELLED", _attr(unpacked, "message"))
            if not _attr(unpacked, "success", False):
                record(STAGE_UNPACK, False, "UNPACK_FAILED")
                return finish(False, "UNPACK_FAILED", _attr(unpacked, "message"))
            record(STAGE_UNPACK, True, "OK")
            continue
        if status == "need_decompile":
            _emit_progress(progress, STAGE_DECOMPILE, -1, "")
            decompiled = callbacks.decompile(cancel_check)
            if _attr(decompiled, "code") == "CANCELLED" or _cancelled(cancel_check):
                record(STAGE_DECOMPILE, False, "CANCELLED")
                return finish(False, "CANCELLED", _attr(decompiled, "message"))
            if not _attr(decompiled, "success", False):
                record(STAGE_DECOMPILE, False, "DECOMPILE_FAILED")
                return finish(False, "DECOMPILE_FAILED", _attr(decompiled, "message"))
            record(STAGE_DECOMPILE, True, "OK")
            continue
        break
    else:
        code = "UNPACK_FAILED" if status == "need_unpack" else (
            "DECOMPILE_FAILED" if status == "need_decompile" else "EXTRACT_FAILED"
        )
        record(STAGE_DETECT, False, code)
        return finish(False, code, detect_message)

    record(STAGE_DETECT, status == "ready", status or "DETECT_FAILED")
    if status == "empty":
        return finish(False, "NO_SCRIPT", detect_message)
    if status != "ready":
        return finish(False, "EXTRACT_FAILED", detect_message)

    # auto 只在「上次翻译确实完成」时才走增量：主缓存里只要还有待译条目，
    # 说明上一次运行被中断，主 TL 目录里仍是源文，必须全量抽取再回填。
    has_completed = _has_completed_translation(config)
    try:
        incremental_extract = resolve_extraction_incremental(
            str(incremental or "auto"), has_completed
        )
    except ValueError:
        return finish(False, "EXTRACT_FAILED", str(incremental))
    need_extract = str(incremental) == "full" or not _output_has_rpy(config)
    extracted_this_run = bool(need_extract)
    did_incremental_extract = False
    if need_extract:
        if _cancelled(cancel_check):
            record(STAGE_EXTRACT, False, "CANCELLED")
            return finish(False, "CANCELLED")
        _emit_progress(progress, STAGE_EXTRACT, -1, "")
        extracted = callbacks.extract(incremental_extract, cancel_check, progress or (lambda *_args: None))
        if _attr(extracted, "code") == "CANCELLED" or _cancelled(cancel_check):
            record(STAGE_EXTRACT, False, "CANCELLED")
            return finish(False, "CANCELLED", _attr(extracted, "message"))
        if not _attr(extracted, "success", False):
            record(STAGE_EXTRACT, False, "EXTRACT_FAILED")
            return finish(False, "EXTRACT_FAILED", _attr(extracted, "message"))
        record(STAGE_EXTRACT, True, "OK")
        did_incremental_extract = bool(incremental_extract)
    else:
        record(STAGE_EXTRACT, True, "SKIPPED")

    # 不在这里用缓存里的「待译 0 条」做跳过判断：抽取刚写完 TL 时缓存还没
    # 重建，新条目并不在缓存里，跳过会让整盘翻译静默不发生。宁可让引擎空跑
    # 一次（它自己只处理 UNTRANSLATED），也不冒漏译的风险。
    if True:
        if _cancelled(cancel_check):
            record(STAGE_TRANSLATE, False, "CANCELLED")
            return finish(False, "CANCELLED")
        _emit_progress(progress, STAGE_TRANSLATE, 0, "")
        accepted = callbacks.start_translation({
            "status": "untranslated",
            "preflight_confirmed": bool(preflight_confirmed),
            "platform_source": "agent" if use_agent_model else "configured",
        })
        if not isinstance(accepted, dict) or not accepted.get("accepted"):
            reason = str((accepted or {}).get("reason") or "ERROR") if isinstance(accepted, dict) else "ERROR"
            detail = str((accepted or {}).get("detail") or "") if isinstance(accepted, dict) else ""
            record(STAGE_TRANSLATE, False, "TRANSLATION_REJECTED")
            return finish(
                False,
                "TRANSLATION_REJECTED",
                detail or reason,
                reason=reason,
                detail=detail,
            )
        started = False
        idle_since = 0.0
        while True:
            if _cancelled(cancel_check):
                try:
                    callbacks.stop_translation()
                except Exception as exc:
                    LogManager.get().error(f"流水线停止翻译失败: {exc}")
                _wait_until_idle()
                record(STAGE_TRANSLATE, False, "CANCELLED")
                return finish(False, "CANCELLED")
            state = callbacks.translation_state() or {}
            progress_data = state.get("progress") if isinstance(state.get("progress"), dict) else {}
            _emit_progress(
                progress,
                STAGE_TRANSLATE,
                _percent(progress_data),
                _translate_detail(progress_data),
            )
            starting = not _engine_idle() or _engine_starting()
            if starting:
                started = True
                idle_since = 0.0
            elif started:
                break
            elif (
                not extracted_this_run
                and state.get("cache_ready")
                and int(state.get("untranslated_count") or 0) == 0
            ):
                # 本轮没抽取过，缓存又是真实存在的「已全部译完」：翻译线程可能
                # 在第一次轮询前就跑完了。抽取过的轮次不能信旧缓存。
                break
            elif idle_since <= 0:
                idle_since = time.monotonic()
            elif time.monotonic() - idle_since >= START_GRACE_SECONDS:
                # 请求已受理但线程始终没起来：宁可报错，也不能把未翻译的目录回填。
                record(STAGE_TRANSLATE, False, "TRANSLATION_NOT_STARTED")
                return finish(False, "TRANSLATION_NOT_STARTED")
            _sleep(POLL_SECONDS)
        state = callbacks.translation_state() or {}
        progress_data = state.get("progress") if isinstance(state.get("progress"), dict) else {}
        line = progress_data.get("line")
        translated_count = int(line) if isinstance(line, int) else 0
        untranslated = int(state.get("untranslated_count") or 0)
        if untranslated > 0:
            record(STAGE_TRANSLATE, False, "TRANSLATION_INCOMPLETE")
            return finish(
                False,
                "TRANSLATION_INCOMPLETE",
                str(untranslated),
                untranslated_count=untranslated,
                progress=progress_data,
            )
        record(STAGE_TRANSLATE, True, "OK")

    if pipeline_identity(config) != identity:
        return finish(False, "PROJECT_CHANGED")

    apply_mode = "incremental" if did_incremental_extract else "full"
    if auto_apply:
        if _cancelled(cancel_check):
            record(STAGE_APPLY, False, "CANCELLED")
            return finish(False, "CANCELLED")
        if not _engine_idle():
            record(STAGE_APPLY, False, "ENGINE_BUSY")
            return finish(False, "ENGINE_BUSY")
        _emit_progress(progress, STAGE_APPLY, -1, "")
        applied = callbacks.apply(apply_mode)
        if not _attr(applied, "success", False):
            code = str(_attr(applied, "code") or "APPLY_FAILED")
            if code == "CANCELLED":
                record(STAGE_APPLY, False, "CANCELLED")
                return finish(False, "CANCELLED", _attr(applied, "message"))
            record(STAGE_APPLY, False, "APPLY_FAILED")
            return finish(False, "APPLY_FAILED", _attr(applied, "message"))
        payload = _attr(applied, "data", {}) or {}
        if isinstance(payload, dict):
            for key in ("applied_count", "count", "files"):
                value = payload.get(key)
                if isinstance(value, int) and value >= 0:
                    applied_files = value
                    break
        record(STAGE_APPLY, True, "OK")
    if auto_fallback and auto_apply:
        if _cancelled(cancel_check):
            record(STAGE_FALLBACK, False, "CANCELLED")
            return finish(False, "CANCELLED")
        _emit_progress(progress, STAGE_FALLBACK, -1, "")
        refreshed = callbacks.fallback()
        if not _attr(refreshed, "success", False):
            record(STAGE_FALLBACK, False, "FALLBACK_FAILED")
            return finish(False, "FALLBACK_FAILED", _attr(refreshed, "message"))
        payload = _attr(refreshed, "data", {}) or {}
        if isinstance(payload, dict):
            for key in ("pair_count", "count", "replace_count"):
                value = payload.get(key)
                if isinstance(value, int) and value >= 0:
                    fallback_count = value
                    break
        record(STAGE_FALLBACK, True, "OK")
    elif auto_fallback and not auto_apply:
        record(STAGE_FALLBACK, True, "SKIPPED")

    _emit_progress(progress, STAGE_DONE, 100, "")
    record(STAGE_DONE, True, "OK")
    return finish(True, "OK")
