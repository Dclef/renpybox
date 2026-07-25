import os
import time
import json
import threading

from base.Base import Base
from module.Config import Config
from module.Cache.CacheDB import CacheDB
from module.Cache.CacheItem import CacheItem
from module.Cache.CacheProject import CacheProject
from module.Localizer.Localizer import Localizer


class CacheLoadError(RuntimeError):
    """Raised when an existing cache cannot be loaded without data loss."""


class CacheManager(Base):

    # 缓存文件保存周期（秒）
    SAVE_INTERVAL = 15

    # SQLite 缓存文件名
    CACHE_DB_NAME = "cache.db"
    RESET_JOURNAL_NAME = "reset.journal.json"

    # 结尾标点符号
    END_LINE_PUNCTUATION = (
        ".",
        "。",
        "?",
        "？",
        "!",
        "！",
        "…",
        "'",
        "\"",
        "’",
        "”",
        "」",
        "』",
        # 追加常见的“行尾收束”符号，让更多对话/旁白行也能成为参考上文，
        # 避免上下文过度稀疏导致译文不连贯。
        ")",
        "）",
        "】",
        "》",
        "〉",
        "—",
        "～",
        "~",
    )

    # 类线程锁
    LOCK = threading.RLock()

    def __init__(self, service: bool) -> None:
        super().__init__()

        # 默认值
        self.project: CacheProject = CacheProject()
        self.items: list[CacheItem] = []
        self.cache_use_sqlite: bool = True
        try:
            self.cache_use_sqlite = bool(Config().load().cache_use_sqlite)
        except Exception:
            self.cache_use_sqlite = True
        # 某个缓存目录的 SQLite 读取失败且 JSON 回退成功后，当前实例后续
        # 的保存与重置都继续使用 JSON，避免坏 cache.db 再次遮蔽有效缓存。
        self._json_fallback_paths: set[str] = set()

        # 初始化
        self.require_flag: bool = False
        self.require_path: str = ""
        self.last_require_time: float = 0

        # 启动定时任务
        if service == True:
            threading.Thread(
                target = self.task,
                daemon = True,
            ).start()

    # 保存缓存到文件的定时任务
    def task(self) -> None:
        while True:
            # 休眠 1 秒
            time.sleep(1.00)

            if self._run_pending_save():
                # 触发事件
                self.emit(Base.Event.CACHE_FILE_AUTO_SAVE, {})

    def _run_pending_save(self, *, now: float | None = None) -> bool:
        current_time = time.time() if now is None else now
        with __class__.LOCK:
            if (
                current_time - self.last_require_time < __class__.SAVE_INTERVAL
                or self.require_flag is not True
            ):
                return False

            output_folder = self.require_path
            try:
                saved = self.save_to_file(
                    project = self.project,
                    items = self.items,
                    output_folder = output_folder,
                )
            except Exception as exc:
                # 自动保存不能让后台服务线程退出；保留 pending 标记，
                # 下一轮继续重试，同时更新时间戳避免每秒重复打磁盘。
                self.debug("自动保存缓存失败，将在下一周期重试", exc)
                self.last_require_time = current_time
                return False

            if saved is not True:
                # save_to_file 在非 strict 模式下会吞掉磁盘/数据库错误，
                # 这里必须识别失败，否则会把“保存失败”误报为成功并清除重试标记。
                self.last_require_time = current_time
                return False

            self.require_flag = False
            self.last_require_time = current_time
            return True

    def _get_db_path(self, output_folder: str) -> str:
        return f"{output_folder}/cache/{__class__.CACHE_DB_NAME}"

    def _get_cache_path_key(self, output_folder: str) -> str:
        return os.path.normcase(os.path.abspath(output_folder))

    def _mark_json_fallback(self, output_folder: str) -> None:
        self._json_fallback_paths.add(self._get_cache_path_key(output_folder))

    def _should_use_sqlite(self, output_folder: str) -> bool:
        if self._get_cache_path_key(output_folder) in self._json_fallback_paths:
            return False
        if os.path.isfile(self._get_db_path(output_folder)):
            return True
        return self.cache_use_sqlite

    def _load_items_from_sqlite(self, output_path: str) -> list[CacheItem] | None:
        db_path = self._get_db_path(output_path)
        if not os.path.isfile(db_path):
            return None
        store = CacheDB(db_path)
        return store.get_items()

    def _load_project_from_sqlite(self, output_path: str) -> CacheProject | None:
        db_path = self._get_db_path(output_path)
        if not os.path.isfile(db_path):
            return None
        store = CacheDB(db_path)
        return store.get_project()

    def _save_items_to_sqlite(self, output_path: str, items: list[CacheItem]) -> None:
        store = CacheDB(self._get_db_path(output_path))
        store.set_items(items)

    def _save_project_to_sqlite(self, output_path: str, project: CacheProject) -> None:
        store = CacheDB(self._get_db_path(output_path))
        store.set_project(project)

    # 保存缓存到文件
    def save_to_file(
        self,
        project: CacheProject,
        items: list[CacheItem],
        output_folder: str,
        *,
        strict: bool = False,
    ) -> bool:
        output_folder = str(output_folder or "").strip()
        if output_folder == "":
            if strict:
                raise ValueError("缓存输出目录不能为空")
            self.debug("跳过缓存保存：输出目录为空")
            return False

        # 创建上级文件夹
        os.makedirs(f"{output_folder}/cache", exist_ok = True)

        # 优先写入 SQLite 缓存
        if self._should_use_sqlite(output_folder):
            with __class__.LOCK:
                try:
                    CacheDB(self._get_db_path(output_folder)).set_translation_cache(
                        project,
                        items,
                    )
                    if strict:
                        db_path = self._get_db_path(output_folder)
                        saved_project = CacheDB(db_path).get_project()
                        if not os.path.isfile(db_path) or saved_project is None:
                            raise RuntimeError("缓存保存后未找到有效的 SQLite 项目记录")
                    self.require_flag = False
                    self.last_require_time = time.time()
                    return True
                except Exception as e:
                    self.debug(Localizer.get().log_write_cache_file_fail, e)
                    if strict:
                        raise RuntimeError(f"SQLite 缓存保存失败：{e}") from e
                    # 已选择 SQLite 时不能再写一份会被旧数据库遮蔽的 JSON；
                    # 保留原缓存并等待下一次自动保存重试。
                    return False

        # JSON 模式使用写前事务日志。若进程在两次文件替换之间退出，
        # 下次内部读取会先恢复同一代 project/items。
        with __class__.LOCK:
            try:
                self._save_translation_run_to_json(output_folder, project, items)
            except Exception as e:
                self.debug(Localizer.get().log_write_cache_file_fail, e)
                if strict:
                    raise RuntimeError(f"缓存保存失败：{e}") from e
                # 非 strict 保存失败时也要保留 pending 标记，供后台重试。
                return False

        if strict:
            cache_path = os.path.join(output_folder, "cache")
            if not (
                os.path.isfile(os.path.join(cache_path, "items.json"))
                and os.path.isfile(os.path.join(cache_path, "project.json"))
            ):
                raise RuntimeError("缓存保存后未找到 JSON 文件")

        # 只有完成写后校验才清除 pending 标记；校验失败时保留标记，
        # 让后台自动保存仍可在下一周期重试。
        self.require_flag = False
        self.last_require_time = time.time()
        return True

    # 请求保存缓存到文件
    def require_save_to_file(self, output_path: str) -> None:
        output_path = str(output_path or "").strip()
        if output_path == "":
            raise ValueError("缓存输出目录不能为空")
        with __class__.LOCK:
            self.require_flag = True
            self.require_path = output_path

    # 从文件读取数据
    def load_from_file(self, output_path: str, *, strict: bool = False) -> None:
        output_path = str(output_path or "").strip()
        if output_path == "":
            if strict:
                raise CacheLoadError("缓存输出目录不能为空")
            return
        if strict:
            self._load_cache_pair_strict(output_path)
            return
        self.load_items_from_file(output_path)
        self.load_project_from_file(output_path)

    def _load_json_cache_pair_strict(
        self,
        output_path: str,
    ) -> tuple[CacheProject, list[CacheItem]]:
        """严格读取 JSON 缓存对，供 SQLite 损坏时安全回退。"""
        self._recover_json_transaction(output_path)
        items_path = f"{output_path}/cache/items.json"
        project_path = f"{output_path}/cache/project.json"
        if not os.path.isfile(items_path) or not os.path.isfile(project_path):
            raise CacheLoadError("Translation cache is incomplete")
        with open(items_path, "r", encoding = "utf-8-sig") as reader:
            items_payload = json.load(reader)
        with open(project_path, "r", encoding = "utf-8-sig") as reader:
            project_payload = json.load(reader)
        if not isinstance(items_payload, list) or not isinstance(project_payload, dict):
            raise CacheLoadError("Translation cache has an invalid schema")
        items = [CacheItem.from_dict(item) for item in items_payload]
        project = CacheProject.from_dict(project_payload)
        return project, items

    def _sqlite_items_conflict_with_json(
        self,
        output_path: str,
        items: list[CacheItem],
        *,
        sqlite_digest: str | None = None,
    ) -> bool:
        """检测明显只有项目记录的半成品 SQLite。

        SQLite 与 JSON 可能来自不同的翻译代次：用户重新抽取、增量合并
        或切换存储后，两边条目数量暂时不同是正常现象，不能再用数量差异
        作为回退条件。只有 SQLite 明确没有任何条目、而 JSON 有完整条目
        时，才可判定为“项目记录已写入、条目尚未写入”的半成品。
        """
        path = f"{output_path}/cache/items.json"
        if not os.path.isfile(path):
            return False
        try:
            with open(path, "r", encoding = "utf-8-sig") as reader:
                payload = json.load(reader)
            if not isinstance(payload, list):
                return False
            # 新版 SQLite 在同一事务写入摘要；摘要存在即代表条目集合
            # 是一个完整代次，即使旧 JSON 数量不同也应以 SQLite 为准。
            if sqlite_digest:
                return False
            return len(payload) > 0 and len(items) == 0
        except Exception:
            return False

    def _load_cache_pair_strict(self, output_path: str) -> None:
        with __class__.LOCK:
            try:
                db_path = self._get_db_path(output_path)
                if os.path.isfile(db_path) and self._should_use_sqlite(output_path):
                    try:
                        store = CacheDB(db_path)
                        project = store.get_project()
                        if project is None:
                            raise CacheLoadError("SQLite cache has no project record")
                        items = store.get_items()
                        if self._sqlite_items_conflict_with_json(
                            output_path,
                            items,
                            sqlite_digest = store.get_items_digest(),
                        ):
                            raise CacheLoadError("SQLite cache items are incomplete")
                    except Exception as sqlite_exc:
                        # SQLite 写入可能在项目记录和条目表之间中断；若同目录
                        # 仍有完整 JSON 事务，则回退到 JSON，避免校对页被残缺
                        # 的 cache.db 永久遮蔽。
                        try:
                            project, items = self._load_json_cache_pair_strict(output_path)
                        except Exception:
                            raise sqlite_exc
                        self._mark_json_fallback(output_path)
                else:
                    project, items = self._load_json_cache_pair_strict(output_path)
            except CacheLoadError:
                raise
            except Exception as exc:
                raise CacheLoadError(
                    f"Failed to load translation cache from {output_path}"
                ) from exc

            self.items = items
            self.project = project

    # 从文件读取项目数据
    def load_items_from_file(self, output_path: str, *, strict: bool = False) -> None:
        output_path = str(output_path or "").strip()
        if output_path == "":
            if strict:
                raise CacheLoadError("缓存输出目录不能为空")
            return
        if strict:
            with __class__.LOCK:
                try:
                    db_path = self._get_db_path(output_path)
                    if os.path.isfile(db_path) and self._should_use_sqlite(output_path):
                        try:
                            store = CacheDB(db_path)
                            items = store.get_items()
                            if self._sqlite_items_conflict_with_json(
                                output_path,
                                items,
                                sqlite_digest = store.get_items_digest(),
                            ):
                                raise CacheLoadError("SQLite cache items are incomplete")
                            self.items = items
                        except Exception as sqlite_exc:
                            # 质量任务可能只读取 items；坏 SQLite 不能遮蔽
                            # 同目录仍完整的 JSON 事务缓存。
                            try:
                                _, items = self._load_json_cache_pair_strict(output_path)
                                self.items = items
                            except Exception:
                                raise sqlite_exc
                            self._mark_json_fallback(output_path)
                        return
                    self._recover_json_transaction(output_path)
                    path = f"{output_path}/cache/items.json"
                    if not os.path.isfile(path):
                        raise CacheLoadError("Cache items do not exist")
                    with open(path, "r", encoding = "utf-8-sig") as reader:
                        payload = json.load(reader)
                    if not isinstance(payload, list):
                        raise CacheLoadError("Cache items must be an array")
                    self.items = [CacheItem.from_dict(item) for item in payload]
                    return
                except CacheLoadError:
                    raise
                except Exception as exc:
                    raise CacheLoadError(
                        f"Failed to load cache items from {output_path}"
                    ) from exc

        use_sqlite = self._should_use_sqlite(output_path)
        sqlite_read_failed = False
        if use_sqlite:
            with __class__.LOCK:
                try:
                    items = self._load_items_from_sqlite(output_path)
                    if items is not None:
                        self.items = items
                        return
                except Exception as e:
                    sqlite_read_failed = True
                    self.debug(Localizer.get().log_read_cache_file_fail, e)

        path = f"{output_path}/cache/items.json"
        with __class__.LOCK:
            try:
                self._recover_json_transaction(output_path)
                if os.path.isfile(path):
                    with open(path, "r", encoding = "utf-8-sig") as reader:
                        self.items = [CacheItem.from_dict(item) for item in json.load(reader)]
                    if sqlite_read_failed:
                        self._mark_json_fallback(output_path)
                    elif use_sqlite:
                        try:
                            self._save_items_to_sqlite(output_path, self.items)
                        except Exception as e:
                            # JSON 已成功载入时，迁移写入失败不应让后续保存
                            # 继续撞向同一个不可用的 SQLite。
                            self._mark_json_fallback(output_path)
                            self.debug(Localizer.get().log_write_cache_file_fail, e)
            except Exception as e:
                self.debug(Localizer.get().log_read_cache_file_fail, e)

    # 从文件读取项目数据
    def load_project_from_file(self, output_path: str, *, strict: bool = False) -> None:
        output_path = str(output_path or "").strip()
        if output_path == "":
            if strict:
                raise CacheLoadError("缓存输出目录不能为空")
            return
        if strict:
            with __class__.LOCK:
                try:
                    db_path = self._get_db_path(output_path)
                    if os.path.isfile(db_path) and self._should_use_sqlite(output_path):
                        try:
                            project = CacheDB(db_path).get_project()
                            if project is None:
                                raise CacheLoadError("SQLite cache has no project record")
                            self.project = project
                        except Exception as sqlite_exc:
                            # 质量任务先读取项目快照；坏 SQLite 时回退到
                            # 同目录 JSON，避免校对页无法恢复语义。
                            try:
                                project, _ = self._load_json_cache_pair_strict(output_path)
                                self.project = project
                            except Exception:
                                raise sqlite_exc
                            self._mark_json_fallback(output_path)
                        return
                    self._recover_json_transaction(output_path)
                    path = f"{output_path}/cache/project.json"
                    if not os.path.isfile(path):
                        raise CacheLoadError("Cache project does not exist")
                    with open(path, "r", encoding = "utf-8-sig") as reader:
                        payload = json.load(reader)
                    if not isinstance(payload, dict):
                        raise CacheLoadError("Cache project must be an object")
                    self.project = CacheProject.from_dict(payload)
                    return
                except CacheLoadError:
                    raise
                except Exception as exc:
                    raise CacheLoadError(
                        f"Failed to load cache project from {output_path}"
                    ) from exc

        use_sqlite = self._should_use_sqlite(output_path)
        sqlite_read_failed = False
        if use_sqlite:
            with __class__.LOCK:
                try:
                    project = self._load_project_from_sqlite(output_path)
                    if project is not None:
                        self.project = project
                        return
                except Exception as e:
                    sqlite_read_failed = True
                    self.debug(Localizer.get().log_read_cache_file_fail, e)

        path = f"{output_path}/cache/project.json"
        with __class__.LOCK:
            try:
                self._recover_json_transaction(output_path)
                if os.path.isfile(path):
                    with open(path, "r", encoding = "utf-8-sig") as reader:
                        self.project = CacheProject.from_dict(json.load(reader))
                    if sqlite_read_failed:
                        self._mark_json_fallback(output_path)
                    elif use_sqlite:
                        try:
                            self._save_project_to_sqlite(output_path, self.project)
                        except Exception as e:
                            self._mark_json_fallback(output_path)
                            self.debug(Localizer.get().log_write_cache_file_fail, e)
            except Exception as e:
                self.debug(Localizer.get().log_read_cache_file_fail, e)

    # 设置缓存数据
    def set_items(self, items: list[CacheItem]) -> None:
        self.items = items

    # 获取缓存数据
    def get_items(self) -> list[CacheItem]:
        return self.items

    # 设置项目数据
    def set_project(self, project: CacheProject) -> None:
        self.project = project

    # 获取项目数据
    def get_project(self) -> CacheProject:
        return self.project

    def reset_translation_run(
        self,
        items: list[CacheItem] | None = None,
        output_path: str | None = None,
        snapshot: object = None,
        progress: dict | None = None,
    ) -> CacheProject:
        """
        Replace data owned by one translation run while retaining project assets.

        Callers that re-read source files should pass the replacement items. When
        ``items`` is omitted, item content is left untouched and only run metadata
        is reset. SQLite persists both records in one transaction. The JSON
        fallback uses a write-ahead journal so interrupted cross-file replacement
        is recovered before the next internal read.
        """
        with __class__.LOCK:
            replacement_items = list(self.items if items is None else items)

            if output_path:
                if self._should_use_sqlite(output_path):
                    try:
                        store = CacheDB(self._get_db_path(output_path))
                        reset_project = store.reset_translation_run(
                            self.project,
                            replacement_items,
                            snapshot = snapshot,
                            progress = progress,
                        )
                    except Exception as exc:
                        # 坏 SQLite 与严格读取使用同一 JSON 回退策略，
                        # 重新开始翻译时也不能让旧数据库遮蔽有效条目。
                        self._mark_json_fallback(output_path)
                        self.debug(Localizer.get().log_write_cache_file_fail, exc)
                        reset_project = CacheProject.from_dict(self.project.asdict())
                        reset_project.reset_translation_run(
                            snapshot = snapshot,
                            progress = progress,
                        )
                        self._save_translation_run_to_json(
                            output_path,
                            reset_project,
                            replacement_items,
                        )
                else:
                    reset_project = CacheProject.from_dict(self.project.asdict())
                    reset_project.reset_translation_run(
                        snapshot = snapshot,
                        progress = progress,
                    )
                    self._save_translation_run_to_json(
                        output_path,
                        reset_project,
                        replacement_items,
                    )
            else:
                reset_project = CacheProject.from_dict(self.project.asdict())
                reset_project.reset_translation_run(
                    snapshot = snapshot,
                    progress = progress,
                )

            self.project = reset_project
            self.items = replacement_items
            self.require_flag = False
            self.last_require_time = time.time()
            return reset_project

    def _save_translation_run_to_json(
        self,
        output_path: str,
        project: CacheProject,
        items: list[CacheItem],
    ) -> None:
        cache_path = os.path.join(output_path, "cache")
        os.makedirs(cache_path, exist_ok = True)

        items_path = os.path.join(cache_path, "items.json")
        project_path = os.path.join(cache_path, "project.json")
        items_temp = f"{items_path}.reset.tmp"
        project_temp = f"{project_path}.reset.tmp"
        journal_path = os.path.join(cache_path, __class__.RESET_JOURNAL_NAME)
        journal_temp = f"{journal_path}.tmp"
        payload = {
            "project": project.asdict(),
            "items": [item.asdict() for item in items],
        }
        try:
            with open(journal_temp, "w", encoding = "utf-8") as writer:
                json.dump(payload, writer, ensure_ascii = False, separators = (",", ":"))
                writer.flush()
                os.fsync(writer.fileno())
            os.replace(journal_temp, journal_path)

            with open(items_temp, "w", encoding = "utf-8") as writer:
                json.dump(
                    payload["items"],
                    writer,
                    ensure_ascii = False,
                    separators = (",", ":"),
                )
            with open(project_temp, "w", encoding = "utf-8") as writer:
                json.dump(payload["project"], writer, ensure_ascii = False, separators = (",", ":"))

            os.replace(items_temp, items_path)
            os.replace(project_temp, project_path)
            os.remove(journal_path)
        finally:
            for temp_path in (items_temp, project_temp, journal_temp):
                if os.path.isfile(temp_path):
                    os.remove(temp_path)

    def _recover_json_transaction(self, output_path: str) -> None:
        cache_path = os.path.join(output_path, "cache")
        journal_path = os.path.join(cache_path, __class__.RESET_JOURNAL_NAME)
        if not os.path.isfile(journal_path):
            return

        with open(journal_path, "r", encoding = "utf-8-sig") as reader:
            payload = json.load(reader)
        if (
            not isinstance(payload, dict)
            or not isinstance(payload.get("project"), dict)
            or not isinstance(payload.get("items"), list)
        ):
            raise ValueError("Invalid cache reset transaction journal")

        items_path = os.path.join(cache_path, "items.json")
        project_path = os.path.join(cache_path, "project.json")
        items_temp = f"{items_path}.recover.tmp"
        project_temp = f"{project_path}.recover.tmp"
        try:
            with open(items_temp, "w", encoding = "utf-8") as writer:
                json.dump(payload["items"], writer, ensure_ascii = False, separators = (",", ":"))
            with open(project_temp, "w", encoding = "utf-8") as writer:
                json.dump(payload["project"], writer, ensure_ascii = False, separators = (",", ":"))
            os.replace(items_temp, items_path)
            os.replace(project_temp, project_path)
            os.remove(journal_path)
        finally:
            for temp_path in (items_temp, project_temp):
                if os.path.isfile(temp_path):
                    os.remove(temp_path)

    # 获取缓存数据数量
    def get_item_count(self) -> int:
        return len(self.items)

    # 复制缓存数据
    def copy_items(self) -> list[CacheItem]:
        return [CacheItem.from_dict(item.asdict()) for item in self.items]

    # 获取缓存数据数量（根据翻译状态）
    def get_item_count_by_status(self, status: int) -> int:
        return len([item for item in self.items if item.get_status() == status])

    # 重置原译相同的条目（用于重新翻译被AI安全规则阻止的内容）
    def reset_same_translation_items(self) -> int:
        """
        将所有"译文等于原文"的已翻译条目重置为未翻译状态
        返回重置的条目数量
        """
        count = 0
        for item in self.items:
            if Base.is_item_completed(item.get_status()):
                src = (item.get_src() or "").strip()
                dst = (item.get_dst() or "").strip()
                if src and dst and src == dst:
                    item.reset_translation()
                    count += 1
        return count

    # 生成缓存数据条目片段
    def generate_item_chunks(self, line_threshold: int, preceding_lines_threshold: int) -> list[list[CacheItem]]:
        # 行数上限：line_threshold 是用户设置的"每批最多 N 行"
        line_limit = max(1, line_threshold)
        # Token 上限：按行数阈值乘以经验系数推算；单行平均约 30-50 token，
        # 乘 16 使短文本不会因 token 超限而过度切分。
        token_limit = max(64, line_threshold * 16)

        skip: int = 0
        line_length: int = 0
        token_length: int = 0
        chunk: list[CacheItem] = []
        chunks: list[list[CacheItem]] = []
        preceding_chunks: list[list[CacheItem]] = []
        for i, item in enumerate(self.items):
            # 跳过状态不是 未翻译 的数据
            if item.get_status() != Base.TranslationStatus.UNTRANSLATED:
                skip = skip + 1
                continue

            # 跳过源文本为空或只有空白字符的条目，并标记为已翻译（空翻译）
            src_text = item.get_src()
            if not src_text or not src_text.strip():
                item.set_dst("")  # 设置空翻译
                item.set_status(Base.TranslationStatus.TRANSLATED)  # 标记为已翻译
                skip = skip + 1
                continue

            # 每个片段的第一条不判断是否超限，以避免特别长的文本导致死循环
            current_line_length = sum(1 for line in src_text.splitlines() if line.strip())
            current_token_length = item.get_token_count()
            if len(chunk) == 0:
                pass
            # 如果 行数超限 或 Token 超限 或 数据来源跨文件，则结束此片段
            elif (
                line_length + current_line_length > line_limit
                or token_length + current_token_length > token_limit
                or item.get_file_path() != chunk[-1].get_file_path()
            ):
                chunks.append(chunk)
                preceding_chunks.append(self.generate_preceding_chunks(chunk, i, skip, preceding_lines_threshold))
                skip = 0

                chunk = []
                line_length = 0
                token_length = 0

            chunk.append(item)
            line_length = line_length + current_line_length
            token_length = token_length + current_token_length

        # 如果还有剩余数据，则添加到列表中
        if len(chunk) > 0:
            chunks.append(chunk)
            preceding_chunks.append(self.generate_preceding_chunks(chunk, i + 1, skip, preceding_lines_threshold))
            skip = 0

        return chunks, preceding_chunks

    # 生成参考上文数据条目片段
    def generate_preceding_chunks(self, chunk: list[CacheItem], start: int, skip: int, preceding_lines_threshold: int) -> list[list[CacheItem]]:
        result: list[CacheItem] = []

        for i in range(start - skip - len(chunk) - 1, -1, -1):
            item = self.items[i]

            # 跳过 已排除 的数据
            if item.get_status() == Base.TranslationStatus.EXCLUDED:
                continue

            # 跳过空数据
            src = item.get_src().strip()
            if src == "":
                continue

            # 候选数据超过阈值时，结束搜索
            if len(result) >= preceding_lines_threshold:
                break

            # 候选数据与当前任务不在同一个文件时，结束搜索
            if item.get_file_path() != chunk[-1].get_file_path():
                break

            # 候选数据以指定标点结尾时，添加到结果中；不以标点结尾时跳过继续搜索
            if src.endswith(__class__.END_LINE_PUNCTUATION):
                result.append(item)

        # 简单逆序
        return result[::-1]
