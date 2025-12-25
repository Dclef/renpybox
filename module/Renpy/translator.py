"""
RenpyBox - 翻译管理核心模块
提供批量翻译、文本处理、结果保存等核心功能

Author: RenpyBox Team
Date: 2025-10-20
Version: 0.1.0
"""

import os
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Callable
from datetime import datetime
from PyQt5.QtCore import QObject, pyqtSignal, QThread

from module.Engine.TaskRequester import TaskRequester
from base.LogManager import LogManager
from module.Translate.RenpySourceTranslator import (
    LineType,
    RenpySourceTranslator,
    TranslationEntry,
)

# 获取 logger 实例
logger = LogManager.get()


class TranslationTask(QObject):
    """翻译任务类 - 在后台线程中执行"""
    
    # 信号定义
    started = pyqtSignal()  # 任务开始
    progress = pyqtSignal(int, int, str)  # 进度更新 (当前, 总数, 消息)
    text_translated = pyqtSignal(str, str)  # 单条翻译完成 (原文, 译文)
    finished = pyqtSignal(dict)  # 任务完成 (结果字典)
    error = pyqtSignal(str)  # 错误发生
    
    def __init__(self, 
                 source_files: List[str],
                 target_language: str,
                 engine_name: str,
                 params: dict):
        super().__init__()
        self.source_files = source_files
        self.target_language = target_language
        self.engine_name = engine_name
        self.params = params
        self.should_stop = False
        
    def stop(self):
        """停止任务"""
        self.should_stop = True
        
    def run(self):
        """执行翻译任务"""
        try:
            self.started.emit()
            logger.info(f"开始翻译任务: {len(self.source_files)} 个文件")
            
            # 1. 读取源文本
            texts = self._read_source_texts()
            if not texts:
                self.error.emit("未找到可翻译文本")
                return
                
            logger.info(f"读取到 {len(texts)} 条文本")
            
            # 2. 预处理文本
            unique_texts = self._preprocess_texts(texts)
            logger.info(f"去重后: {len(unique_texts)} 条独特文本")
            
            # 3. 批量翻译
            translations = self._translate_texts(unique_texts)
            
            if self.should_stop:
                logger.info("翻译任务已取消")
                return
            
            # 4. 后处理和映射回原文本
            final_results = self._postprocess_texts(texts, translations)
            
            # 5. 保存翻译结果
            self._save_translations(final_results)
            
            self.finished.emit(final_results)
            logger.info("翻译任务完成")
            
        except Exception as e:
            logger.error(f"翻译任务出错: {str(e)}", exc_info=True)
            self.error.emit(f"翻译失败: {str(e)}")
    
    def _read_source_texts(self) -> Dict[str, List[Dict]]:
        """读取源文件中的可翻译文本
        
        Returns:
            {
                'file_path': [
                    {'line': 10, 'original': '原文', 'type': 'dialogue'},
                    ...
                ]
            }
        """
        all_texts: Dict[str, List[Dict]] = {}
        parser = RenpySourceTranslator()

        for file_path in self.source_files:
            if self.should_stop:
                break

            try:
                path_obj = Path(file_path)
                if not path_obj.exists():
                    logger.warning(f"文件不存在: {file_path}")
                    continue

                parsed: List[TranslationEntry] = parser.scan_file(path_obj)
                if not parsed:
                    continue

                texts: List[Dict] = []
                pending_old: Optional[str] = None

                for entry in parsed:
                    text = entry.text.strip()
                    if not entry.needs_translation or not text:
                        if entry.line_type != LineType.STRING_BLOCK:
                            pending_old = None
                        continue

                    if entry.line_type == LineType.STRING_BLOCK:
                        if entry.string_is_old:
                            pending_old = entry.text
                            continue

                        original_text = pending_old if pending_old is not None else entry.text
                        texts.append({
                            'line': entry.line_number,
                            'original': original_text,
                            'translation': entry.text if pending_old is not None else "",
                            'type': self._map_line_type(entry.line_type),
                        })
                        pending_old = None
                        continue

                    pending_old = None
                    item = {
                        'line': entry.line_number,
                        'original': entry.text,
                        'type': self._map_line_type(entry.line_type),
                    }
                    if entry.speaker:
                        item['speaker'] = entry.speaker
                    if entry.menu_hints:
                        item['hint'] = entry.menu_hints
                    if entry.menu_condition:
                        item['condition'] = entry.menu_condition
                    texts.append(item)

                if pending_old:
                    texts.append({
                        'line': 0,
                        'original': pending_old,
                        'translation': "",
                        'type': self._map_line_type(LineType.STRING_BLOCK),
                    })

                if texts:
                    all_texts[str(path_obj)] = texts

            except Exception as e:
                logger.error(f"读取文件失败 {file_path}: {str(e)}")

        return all_texts

    @staticmethod
    def _map_line_type(line_type: LineType) -> str:
        mapping = {
            LineType.DIALOGUE: 'dialogue',
            LineType.NARRATION: 'narration',
            LineType.MENU_OPTION: 'menu',
            LineType.STRING_BLOCK: 'string',
        }
        return mapping.get(line_type, 'text')
    
    def _preprocess_texts(self, texts: Dict[str, List[Dict]]) -> List[str]:
        """预处理文本（去重、清理等）
        
        Returns:
            去重后的文本列表
        """
        unique_texts = set()
        
        for file_texts in texts.values():
            for item in file_texts:
                text = item['original']
                # 清理空白字符
                text = text.strip()
                # 已有不同的翻译时跳过，避免重复请求
                existing_translation = item.get('translation', '').strip()
                if existing_translation and existing_translation != text:
                    continue
                if text:
                    unique_texts.add(text)
        
        return list(unique_texts)
    
    def _translate_texts(self, texts: List[str]) -> Dict[str, str]:
        """批量翻译文本
        
        Returns:
            {原文: 译文} 的字典
        """
        translations = {}
        batch_size = self.params.get('batch_size', 10)
        total = len(texts)
        
        # 创建翻译请求器
        requester = TaskRequester(
            engine=self.engine_name,
            model=self.params.get('model', 'gpt-4o-mini'),
            temperature=self.params.get('temperature', 0.3),
            top_p=self.params.get('top_p', 0.95)
        )
        
        # 分批翻译
        for i in range(0, total, batch_size):
            if self.should_stop:
                break
                
            batch = texts[i:i+batch_size]
            batch_num = i // batch_size + 1
            total_batches = (total + batch_size - 1) // batch_size
            
            self.progress.emit(i, total, f"正在翻译第 {batch_num}/{total_batches} 批...")
            
            try:
                # 构建翻译提示
                source_text = "\n".join([f"{idx+1}. {text}" for idx, text in enumerate(batch)])
                prompt = f"""请将以下文本翻译成{self.target_language}，保持原有格式和编号：

{source_text}

要求：
1. 保持编号格式
2. 翻译要符合游戏对话风格
3. 保留特殊标记和格式
"""
                
                # 调用翻译API
                result = requester.make_request(
                    messages=[{"role": "user", "content": prompt}]
                )
                
                if result and result.get('content'):
                    # 解析翻译结果
                    translated_text = result['content']
                    parsed = self._parse_translation_result(batch, translated_text)
                    translations.update(parsed)
                    
                    # 发送单条翻译完成信号
                    for original, translated in parsed.items():
                        self.text_translated.emit(original, translated)
                    
            except Exception as e:
                logger.error(f"翻译批次 {batch_num} 失败: {str(e)}")
                # 失败的批次使用原文
                for text in batch:
                    translations[text] = text
        
        return translations
    
    def _parse_translation_result(self, original_batch: List[str], translated_text: str) -> Dict[str, str]:
        """解析翻译结果
        
        Args:
            original_batch: 原文列表
            translated_text: 翻译后的文本
            
        Returns:
            {原文: 译文} 字典
        """
        result = {}
        lines = translated_text.strip().split('\n')
        
        # 尝试匹配编号格式
        for i, original in enumerate(original_batch):
            target_num = str(i + 1)
            found = False
            
            for line in lines:
                line = line.strip()
                # 匹配 "1. 译文" 或 "1. 译文" 格式
                if line.startswith(f"{target_num}."):
                    translated = line[len(target_num)+1:].strip()
                    result[original] = translated
                    found = True
                    break
            
            # 如果没找到，使用原文
            if not found:
                result[original] = original
                logger.warning(f"未找到编号 {target_num} 的翻译，使用原文")
        
        return result
    
    def _postprocess_texts(self, 
                          original_texts: Dict[str, List[Dict]], 
                          translations: Dict[str, str]) -> Dict[str, List[Dict]]:
        """后处理文本，映射翻译结果回原文本结构
        
        Returns:
            {
                'file_path': [
                    {'line': 10, 'original': '原文', 'translation': '译文', 'type': 'dialogue'},
                    ...
                ]
            }
        """
        results = {}
        
        for file_path, texts in original_texts.items():
            file_results = []
            for item in texts:
                original = item['original']
                translation = translations.get(original, original)  # 默认使用原文
                
                file_results.append({
                    'line': item['line'],
                    'original': original,
                    'translation': translation,
                    'type': item['type']
                })
            
            results[file_path] = file_results
        
        return results
    
    def _save_translations(self, translations: Dict[str, List[Dict]]):
        """保存翻译结果到 game/tl/{language}/ 目录
        
        Args:
            translations: 翻译结果字典
        """
        try:
            # 确定保存路径
            if not self.source_files:
                return
            
            # 假设第一个文件在 game/ 目录下
            first_file = Path(self.source_files[0])
            game_dir = None
            
            # 向上查找 game 目录
            for parent in first_file.parents:
                if parent.name == 'game':
                    game_dir = parent
                    break
            
            if not game_dir:
                logger.warning("未找到 game 目录，翻译结果仅保存在内存中")
                return
            
            # 创建翻译目录
            tl_dir = game_dir / 'tl' / self.target_language
            tl_dir.mkdir(parents=True, exist_ok=True)
            
            # 保存每个文件的翻译
            for file_path, items in translations.items():
                # 计算相对路径
                source_path = Path(file_path)
                try:
                    rel_path = source_path.relative_to(game_dir)
                except ValueError:
                    # 如果不在 game 目录下，使用文件名
                    rel_path = source_path.name
                
                # 创建翻译文件路径
                trans_file = tl_dir / rel_path
                trans_file.parent.mkdir(parents=True, exist_ok=True)
                
                # 生成翻译文件内容
                content = self._generate_translation_file(items)
                
                # 写入文件
                with open(trans_file, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                logger.info(f"翻译已保存: {trans_file}")
                
        except Exception as e:
            logger.error(f"保存翻译失败: {str(e)}", exc_info=True)

    @staticmethod
    def _escape_rpy_string(value: str) -> str:
        return (
            value.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\r\n", "\n")
            .replace("\r", "\n")
            .replace("\n", "\\n")
        )

    def _generate_translation_file(self, items: List[Dict]) -> str:
        """生成 Ren'Py 翻译文件内容
        
        Args:
            items: 翻译项列表
            
        Returns:
            翻译文件内容
        """
        lines = [
            "# TODO: Translation updated at " + datetime.now().strftime("%Y-%m-%d %H:%M"),
            "",
            f"translate {self.target_language} strings:",
            ""
        ]
        
        for item in items:
            original = item['original']
            translation = item['translation']
            
            # 转义写回
            original = self._escape_rpy_string(original)
            translation = self._escape_rpy_string(translation)
            
            lines.append(f'    # Line {item["line"]}')
            lines.append(f'    old "{original}"')
            lines.append(f'    new "{translation}"')
            lines.append('')
        
        return '\n'.join(lines)


class RenpyTranslator(QObject):
    """Ren'Py 翻译管理器 - 主控制类"""
    
    # 信号定义
    translation_started = pyqtSignal()
    progress_updated = pyqtSignal(int, int, str)  # 当前, 总数, 消息
    translation_finished = pyqtSignal(dict)
    translation_error = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.extractor = RenpyExtractor()
        self.current_task: Optional[TranslationTask] = None
        self.thread: Optional[QThread] = None
        
    def start_translation(self,
                         source_files: List[str],
                         target_language: str,
                         engine_name: str,
                         params: dict):
        """启动翻译任务
        
        Args:
            source_files: 源文件路径列表
            target_language: 目标语言 (如 'chinese', 'english')
            engine_name: 引擎名称 (如 'openai', 'claude')
            params: 翻译参数字典
        """
        if self.current_task:
            self.translation_error.emit("已有翻译任务正在运行")
            return
        
        # 创建翻译任务
        self.current_task = TranslationTask(
            source_files=source_files,
            target_language=target_language,
            engine_name=engine_name,
            params=params
        )
        
        # 连接信号
        self.current_task.started.connect(self._on_task_started)
        self.current_task.progress.connect(self._on_task_progress)
        self.current_task.finished.connect(self._on_task_finished)
        self.current_task.error.connect(self._on_task_error)
        
        # 创建线程
        self.thread = QThread()
        self.current_task.moveToThread(self.thread)
        
        # 启动线程
        self.thread.started.connect(self.current_task.run)
        self.thread.start()
        
        logger.info("翻译任务已启动")
    
    def stop_translation(self):
        """停止当前翻译任务"""
        if self.current_task:
            self.current_task.stop()
            logger.info("正在停止翻译任务...")
    
    def _on_task_started(self):
        """任务开始回调"""
        self.translation_started.emit()
    
    def _on_task_progress(self, current: int, total: int, message: str):
        """进度更新回调"""
        self.progress_updated.emit(current, total, message)
    
    def _on_task_finished(self, results: dict):
        """任务完成回调"""
        self.translation_finished.emit(results)
        self._cleanup_task()
    
    def _on_task_error(self, error: str):
        """任务错误回调"""
        self.translation_error.emit(error)
        self._cleanup_task()
    
    def _cleanup_task(self):
        """清理任务和线程"""
        if self.thread:
            self.thread.quit()
            self.thread.wait()
            self.thread = None
        self.current_task = None
        logger.info("翻译任务已清理")
