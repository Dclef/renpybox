"""
极速翻译器 - 使用 pygtrans (Google) 和 translators (Bing) 实现高速翻译
模仿 renpy-translator-main 的实现方式
"""

import os
import re
import concurrent.futures
import traceback
from typing import List, Dict, Optional, Any, Tuple

try:
    from pygtrans import Translate
    PYGTRANS_AVAILABLE = True
except ImportError:
    PYGTRANS_AVAILABLE = False

try:
    # 设置默认区域以避免 translators 库在导入时的地理位置检测失败
    os.environ.setdefault("translators_default_region", "CN")
    import translators as ts
    TRANSLATORS_AVAILABLE = True
except (ImportError, Exception):
    TRANSLATORS_AVAILABLE = False

from base.LogManager import LogManager


class TranslateResponse:
    """翻译响应对象，兼容 renpy-translator-main 格式"""
    def __init__(self, ori: str, res: str):
        self.untranslatedText = ori
        self.translatedText = res


class FastTranslator:
    """
    极速翻译器
    - Google: 使用 pygtrans 库，支持批量翻译
    - Bing: 使用 translators 库
    
    支持占位符保护：[me], [mom], {name}, {{sprite}} 等标签在翻译时会被保护
    """
    
    # 占位符正则：匹配 [xxx], {xxx}, {{xxx}}, %s, %d, %(name)s 等
    PLACEHOLDER_PATTERNS = [
        r'\[\w+\]',           # [me], [mom], [player_name]
        r'\{\{?\w+\}?\}',     # {name}, {{sprite}}
        r'%[\w]*[sdifx]',      # %s, %d, %(name)s
        r'\\n',               # \n 换行符
        r'<[^>]+>',            # <b>, </b>, <color=#fff> HTML标签
    ]
    _PLACEHOLDER_RE = re.compile('|'.join(PLACEHOLDER_PATTERNS))
    
    # 语言代码映射
    LANG_MAP = {
        # 中文显示名 -> pygtrans/translators 代码
        "简体中文": "zh-CN",
        "繁体中文": "zh-TW", 
        "英语": "en",
        "日语": "ja",
        "韩语": "ko",
        "俄语": "ru",
        "法语": "fr",
        "德语": "de",
        "西班牙语": "es",
        "葡萄牙语": "pt",
        # 英文名
        "chinese": "zh-CN",
        "english": "en",
        "japanese": "ja",
        "auto": "auto",
    }
    
    def __init__(self, engine: str = 'google', proxies: Optional[Dict] = None):
        self.engine = engine.lower()
        self.logger = LogManager.get()
        self._client = None
        self._google_failed = False  # 标记 Google 是否连接失败
        self._google_timeout = 15
        
        # 从配置读取代理
        if proxies is None:
            proxies = self._load_proxy_from_config()
        self.proxies = proxies
        
        # 初始化客户端
        if self.engine == 'google' and PYGTRANS_AVAILABLE:
            self._client = Translate(fmt='text', proxies=proxies, timeout=self._google_timeout, trust_env=True)
        elif not TRANSLATORS_AVAILABLE and self.engine != 'google':
            self.logger.warning(f"translators 库不可用，{self.engine} 引擎可能无法工作")
    
    def _load_proxy_from_config(self) -> Optional[Dict]:
        """从配置文件读取代理设置"""
        try:
            from module.Config import Config
            config = Config().load()
            
            # 检查代理是否启用
            proxy_enable = getattr(config, 'proxy_enable', False)
            if not proxy_enable:
                return None
            
            proxy_url = getattr(config, 'proxy_url', None) or getattr(config, 'proxy', None)
            if proxy_url and proxy_url.strip():
                self.logger.info(f"使用代理: {proxy_url}")
                return {
                    'http': proxy_url,
                    'https': proxy_url,
                }
        except Exception as e:
            self.logger.warning(f"读取代理配置失败: {e}")
        return None
    
    def _protect_placeholders(self, text: str) -> Tuple[str, List[Tuple[str, str]]]:
        """
        保护占位符：用唯一标记替换，防止翻译器翻译
        
        Args:
            text: 原始文本
            
        Returns:
            (替换后的文本, [(标记, 原始占位符)...])
        """
        placeholders = []
        counter = [0]  # 用列表以便在内部函数中修改
        
        def replace_func(match):
            original = match.group(0)
            marker = f"\u3010PH{counter[0]:03d}\u3011"  # 使用中文括号作为标记，不太可能被翻译
            placeholders.append((marker, original))
            counter[0] += 1
            return marker
        
        protected_text = self._PLACEHOLDER_RE.sub(replace_func, text)
        return protected_text, placeholders
    
    def _restore_placeholders(self, text: str, placeholders: List[Tuple[str, str]]) -> str:
        """
        还原占位符
        
        Args:
            text: 翻译后的文本
            placeholders: [(标记, 原始占位符)...]
            
        Returns:
            还原占位符后的文本
        """
        result = text
        for marker, original in placeholders:
            result = result.replace(marker, original)
        return result
    
    def _protect_batch(self, texts: List[str]) -> Tuple[List[str], List[List[Tuple[str, str]]]]:
        """
        批量保护占位符
        
        Returns:
            (保护后的文本列表, 每条文本的占位符映射列表)
        """
        protected_texts = []
        all_placeholders = []
        
        for text in texts:
            protected, placeholders = self._protect_placeholders(text)
            protected_texts.append(protected)
            all_placeholders.append(placeholders)
        
        return protected_texts, all_placeholders
    
    def _restore_batch(self, texts: List[str], all_placeholders: List[List[Tuple[str, str]]]) -> List[str]:
        """
        批量还原占位符
        """
        return [
            self._restore_placeholders(text, placeholders)
            for text, placeholders in zip(texts, all_placeholders)
        ]
    
    def translate_batch(
        self,
        texts: List[str],
        target_lang: str,
        source_lang: str = 'auto',
        max_batch_size: Optional[int] = None,
    ) -> List[str]:
        """
        批量翻译文本（带占位符保护）
        
        Args:
            texts: 要翻译的文本列表
            target_lang: 目标语言
            source_lang: 源语言，默认自动检测
            
        Returns:
            翻译后的文本列表
        """
        if not texts:
            return []
        
        target_code = self._map_lang_code(target_lang)
        source_code = self._map_lang_code(source_lang)
        
        # 1. 保护占位符
        protected_texts, all_placeholders = self._protect_batch(texts)
        
        # 2. 执行翻译
        if self.engine == 'google' and not self._google_failed:
            translated = self._translate_google(protected_texts, target_code, source_code)
            # 如果 Google 翻译全部失败（返回原文），尝试 Bing
            if translated == protected_texts and TRANSLATORS_AVAILABLE:
                self.logger.warning("Google 翻译失败，自动切换到 Bing 翻译")
                self._google_failed = True
                translated = self._translate_with_translators(
                    protected_texts,
                    target_code,
                    source_code,
                    max_batch_size,
                )
        elif self._google_failed or self.engine != 'google':
            translated = self._translate_with_translators(
                protected_texts,
                target_code,
                source_code,
                max_batch_size,
            )
        else:
            translated = self._translate_with_translators(
                protected_texts,
                target_code,
                source_code,
                max_batch_size,
            )
        
        # 3. 还原占位符
        return self._restore_batch(translated, all_placeholders)
    
    def _translate_google(self, texts: List[str], target: str, source: str) -> List[str]:
        """
        使用 pygtrans 进行 Google 翻译
        pygtrans 原生支持批量翻译，速度极快
        """
        if not PYGTRANS_AVAILABLE or not self._client:
            self.logger.error("pygtrans 不可用，请安装: pip install pygtrans")
            return texts
        
        try:
            # pygtrans 的 translate 方法支持列表输入
            results = self._client.translate(texts, target=target, source=source, timeout=self._google_timeout)
            
            if isinstance(results, list):
                translated = []
                for i, item in enumerate(results):
                    if hasattr(item, 'translatedText') and item.translatedText:
                        translated.append(item.translatedText)
                    else:
                        # 翻译失败，使用原文
                        translated.append(texts[i] if i < len(texts) else '')
                return translated
            else:
                self.logger.error(f"Google 翻译返回格式异常: {type(results)}")
                return texts
                
        except Exception as e:
            self.logger.error(f"Google 批量翻译失败: {e}")
            # 标记 Google 连接失败，后续自动使用 Bing
            self._google_failed = True
            return texts
    
    def _translate_with_translators(
        self,
        texts: List[str],
        target: str,
        source: str,
        max_batch_size: Optional[int] = None,
        use_engine: str = None,
    ) -> List[str]:
        """
        使用 translators 库进行翻译（Bing 等）
        使用多线程并发加速
        
        Args:
            use_engine: 指定使用的引擎，默认使用 self.engine，如果是 google 则自动切换为 bing
        """
        if not TRANSLATORS_AVAILABLE:
            self.logger.error("translators 库不可用，请安装: pip install translators")
            return texts
        
        # 确定使用的引擎 - translators 库不支持 google，先使用 bing 代替，再按候选回退
        requested_engine = (use_engine or self.engine or "bing").lower()
        if requested_engine == 'google':
            requested_engine = 'bing'

        # 分批处理，允许外部指定最大批大小
        batch_size = max(1, int(max_batch_size or 50))

        # 候选引擎：优先用户指定，其次按可用性回退（translators 6.x 部分引擎会标记为 not certified）
        # 说明：这里仅放入实测更常用、且语言码兼容性较好的引擎作为回退。
        fallback_engines = ("alibaba", "bing", "sogou", "caiyun")
        engine_candidates = [requested_engine] + [e for e in fallback_engines if e != requested_engine]

        best_results: List[str] = texts
        best_changed = -1
        best_engine = requested_engine

        for engine_to_use in engine_candidates:
            all_results: List[str] = []
            total_errors = 0
            total_unchanged = 0
            first_error: Optional[str] = None

            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                batch_results, batch_errors, batch_unchanged, batch_first_error = self._translate_batch_concurrent(
                    batch, target, source, engine_to_use
                )
                all_results.extend(batch_results)
                total_errors += batch_errors
                total_unchanged += batch_unchanged
                if first_error is None and batch_first_error:
                    first_error = batch_first_error

            changed = max(0, len(texts) - total_unchanged)
            if changed > best_changed:
                best_results = all_results
                best_changed = changed
                best_engine = engine_to_use

            if total_errors >= len(texts):
                sample = f"，示例错误: {first_error}" if first_error else ""
                self.logger.warning(f"翻译引擎 {engine_to_use} 全部失败 {total_errors}/{len(texts)} 条{sample}")

            # 如果本引擎完全不可用（全部失败/全部原文），继续尝试下一个
            if changed == 0 and total_errors >= len(texts):
                continue
            # 有任何有效翻译就停止（避免多引擎重复耗时）
            if changed > 0:
                break

        if best_engine != requested_engine and best_changed > 0:
            self.logger.warning(f"翻译引擎不可用，已自动切换: {requested_engine} -> {best_engine}")

        return best_results
    
    def _translate_batch_concurrent(self, texts: List[str], target: str, source: str, engine: str) -> tuple[List[str], int, int, Optional[str]]:
        """
        使用线程池并发翻译
        """
        results: List[Optional[str]] = [None] * len(texts)
        error_count = 0
        unchanged_count = 0
        first_error: Optional[str] = None
        
        def translate_single(index: int, text: str) -> tuple:
            try:
                if not text or not text.strip():
                    return index, text, False, None
                    
                res = ts.translate_text(
                    text,
                    translator=engine,
                    from_language=source,
                    to_language=target,
                    timeout=15
                )
                
                if res and res != text:
                    return index, res, False, None

                return index, text, False, None
                    
            except Exception as e:
                return index, text, True, str(e)
        
        # 使用线程池并发（过高并发容易触发风控或解析异常）
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(translate_single, idx, text)
                for idx, text in enumerate(texts)
            ]
            
            for future in concurrent.futures.as_completed(futures):
                try:
                    idx, result, had_error, error_message = future.result()
                    results[idx] = result

                    if had_error:
                        error_count += 1
                        if first_error is None and error_message:
                            first_error = error_message
                except Exception as e:
                    error_count += 1
                    if first_error is None:
                        first_error = str(e)
        
        # 确保所有结果都有值
        final_results = [
            results[i] if results[i] is not None else texts[i]
            for i in range(len(texts))
        ]

        for src, dst in zip(texts, final_results):
            if dst == src:
                unchanged_count += 1

        return final_results, error_count, unchanged_count, first_error
    
    def _map_lang_code(self, lang_name: str) -> str:
        """映射语言名称到代码"""
        if not lang_name:
            return 'auto'
        return self.LANG_MAP.get(lang_name, lang_name)
