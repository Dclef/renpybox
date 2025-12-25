import os
import time
import json
import threading

from base.Base import Base
from module.Cache.CacheItem import CacheItem
from module.Cache.CacheProject import CacheProject
from module.Localizer.Localizer import Localizer

class CacheManager(Base):

    # 缓存文件保存周期（秒）
    SAVE_INTERVAL = 15

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
    )

    # 类线程锁
    LOCK = threading.Lock()

    def __init__(self, service: bool) -> None:
        super().__init__()

        # 默认值
        self.project: CacheProject = CacheProject()
        self.items: list[CacheItem] = []

        # 初始化
        self.require_flag: bool = False
        self.require_path: str = ""
        self.last_require_time: float = 0

        # 启动定时任务
        if service == True:
            threading.Thread(
                target = self.task,
            ).start()

    # 保存缓存到文件的定时任务
    def task(self) -> None:
        while True:
            # 休眠 1 秒
            time.sleep(1.00)

            if (
                time.time() - self.last_require_time >= __class__.SAVE_INTERVAL
                and self.require_flag == True
            ):
                # 创建上级文件夹
                folder_path = f"{self.require_path}/cache"
                os.makedirs(folder_path, exist_ok = True)

                # 保存缓存到文件
                self.save_to_file(
                    project = self.project,
                    items = self.items,
                    output_folder = self.require_path,
                )

                # 触发事件
                self.emit(Base.Event.CACHE_FILE_AUTO_SAVE, {})

                # 重置标志
                self.require_flag = False
                self.last_require_time = time.time()

    # 保存缓存到文件
    def save_to_file(self, project: CacheProject, items: list[CacheItem], output_folder: str) -> None:
        # 创建上级文件夹
        os.makedirs(f"{output_folder}/cache", exist_ok = True)

        # 保存缓存到文件
        path = f"{output_folder}/cache/items.json"
        with __class__.LOCK:
            try:
                with open(path, "w", encoding = "utf-8") as writer:
                    # 逐条写入以避免一次性构建超大字符串导致 UI 卡顿（线程持有 GIL 时间过长）
                    writer.write("[")
                    for i, item in enumerate(items):
                        if i > 0:
                            writer.write(",")
                        json.dump(item.asdict(), writer, ensure_ascii = False, separators = (",", ":"))

                        # 适当让出执行权，提升停止/切换页面时的响应速度
                        if i % 200 == 0:
                            writer.flush()
                            time.sleep(0)
                    writer.write("]")
            except Exception as e:
                self.debug(Localizer.get().log_write_cache_file_fail, e)

        # 保存项目数据到文件
        path = f"{output_folder}/cache/project.json"
        with __class__.LOCK:
            try:
                with open(path, "w", encoding = "utf-8") as writer:
                    writer.write(json.dumps(project.asdict(), indent = None, ensure_ascii = False))
            except Exception as e:
                self.debug(Localizer.get().log_write_cache_file_fail, e)

        # 重置标志
        self.require_flag = False
        self.last_require_time = time.time()

    # 请求保存缓存到文件
    def require_save_to_file(self, output_path: str) -> None:
        self.require_flag = True
        self.require_path = output_path

    # 从文件读取数据
    def load_from_file(self, output_path: str) -> None:
        self.load_items_from_file(output_path)
        self.load_project_from_file(output_path)

    # 从文件读取项目数据
    def load_items_from_file(self, output_path: str) -> None:
        path = f"{output_path}/cache/items.json"
        with __class__.LOCK:
            try:
                if os.path.isfile(path):
                    with open(path, "r", encoding = "utf-8-sig") as reader:
                        self.items = [CacheItem.from_dict(item) for item in json.load(reader)]
            except Exception as e:
                self.debug(Localizer.get().log_read_cache_file_fail, e)

    # 从文件读取项目数据
    def load_project_from_file(self, output_path: str) -> None:
        path = f"{output_path}/cache/project.json"
        with __class__.LOCK:
            try:
                if os.path.isfile(path):
                    with open(path, "r", encoding = "utf-8-sig") as reader:
                        self.project = CacheProject.from_dict(json.load(reader))
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
            if item.get_status() == Base.TranslationStatus.TRANSLATED:
                src = (item.get_src() or "").strip()
                dst = (item.get_dst() or "").strip()
                if src and dst and src == dst:
                    item.set_status(Base.TranslationStatus.UNTRANSLATED)
                    item.set_dst("")
                    item.set_retry_count(0)
                    count += 1
        return count

    # 生成缓存数据条目片段
    def generate_item_chunks(self, line_threshold: int, preceding_lines_threshold: int) -> list[list[CacheItem]]:
        # 直接使用行数阈值
        line_limit = max(1, line_threshold)

        skip: int = 0
        line_length: int = 0
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
            if len(chunk) == 0:
                pass
            # 如果 行数超限 或 数据来源跨文件，则结束此片段
            elif (
                line_length + current_line_length > line_limit
                or item.get_file_path() != chunk[-1].get_file_path()
            ):
                chunks.append(chunk)
                preceding_chunks.append(self.generate_preceding_chunks(chunk, i, skip, preceding_lines_threshold))
                skip = 0

                chunk = []
                line_length = 0

            chunk.append(item)
            line_length = line_length + current_line_length

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

            # 候选数据以指定标点结尾时，添加到结果中
            if src.endswith(__class__.END_LINE_PUNCTUATION):
                result.append(item)
            else:
                break

        # 简单逆序
        return result[::-1]
