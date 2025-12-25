import os
import json
import re
import time

import opencc

from base.Base import Base
from base.BaseLanguage import BaseLanguage
from module.Text.TextHelper import TextHelper
from module.Cache.CacheItem import CacheItem
from module.Config import Config
from module.Response.ResponseChecker import ResponseChecker
from module.Localizer.Localizer import Localizer
from module.TextProcessor import TextProcessor

class ResultChecker(Base):

    # 类变量
    OPENCCT2S = opencc.OpenCC("t2s")
    OPENCCS2T = opencc.OpenCC("s2tw")
    
    # 检测"英文单词+中文"异常翻译模式的正则
    # 匹配：句首英文单词(2-15个字母)后面直接跟中文字符
    RE_MIXED_TRANSLATION = re.compile(
        r'^["\'\(（]*[A-Z][a-z]{1,14}[\u4e00-\u9fff]',  # 如 "It醒醒", "You我不知道"
        re.UNICODE
    )

    def __init__(self, config: Config, items: list[CacheItem]) -> None:
        super().__init__()

        # 初始化
        self.config: Config = config
        self.text_processor: TextProcessor = TextProcessor(config, None)

        # 筛选数据
        # ResultChecker 只用于结果报告，不应对每条数据重复执行完整的 TextProcessor 预处理（会非常耗时且阻塞 UI）。
        # 这里只做最小化过滤：剔除空/仅空白行的条目。
        self.items_untranslated = [item for item in items if item.get_status() == Base.TranslationStatus.UNTRANSLATED]
        self.items_translated: list[CacheItem] = [
            item for item in items
            if item.get_status() == Base.TranslationStatus.TRANSLATED
            and item.get_src().strip() != ""
        ]

        # 获取译前替换后的原文
        self.src_repls: list[str] = []
        pre_translation_replacement_data: list[dict] = config.pre_translation_replacement_data
        pre_translation_replacement_enable: bool = config.pre_translation_replacement_enable
        for item in self.items_translated:
            src = item.get_src()

            if pre_translation_replacement_enable == True and len(pre_translation_replacement_data) > 0:
                for v in pre_translation_replacement_data:
                    src = src.replace(v.get('src'), v.get('dst'))

            self.src_repls.append(src)

        # 获取译后替换前的译文
        self.dst_repls: list[str] = []
        post_translation_replacement_data: list[dict] = config.post_translation_replacement_data
        post_translation_replacement_enable: bool = config.post_translation_replacement_enable
        for item in self.items_translated:
            dst = item.get_dst()

            if post_translation_replacement_enable == True and len(post_translation_replacement_data) > 0:
                for v in post_translation_replacement_data:
                    dst = dst.replace(v.get('dst'), v.get('src'))

            self.dst_repls.append(dst)

    # 检查
    def check(self) -> None:
        os.makedirs(self.config.output_folder, exist_ok = True)
        [
            os.remove(entry.path)
            for entry in os.scandir(self.config.output_folder)
            if entry.is_file() and entry.name.startswith(("结果检查_", "result_check_"))
        ]

        self.check_kana()
        self.check_hangeul()
        self.check_text_preserve()
        self.check_similarity()
        self.check_glossary()
        self.check_mixed_translation()  # 新增：检查英文+中文混合翻译错误
        self.check_untranslated()
        self.check_retry_count_threshold()

    # 假名残留检查
    def check_kana(self) -> None:
        if self.config.source_language != BaseLanguage.Enum.JA:
            return None

        count = 0
        result: dict[str, str] = {}

        for item in self.items_translated:
            if TextHelper.JA.any_hiragana(item.get_dst()) or TextHelper.JA.any_katakana(item.get_dst()):
                count = count + 1
                result.setdefault(item.get_file_path(), {})[item.get_src()] = item.get_dst()

        if count == 0:
            self.info(Localizer.get().file_checker_kana)
        else:
            target = f"{self.config.output_folder}/{Localizer.get().path_result_check_kana}".replace("\\", "/")
            with open(target, "w", encoding = "utf-8") as writer:
                writer.write(json.dumps(result, indent = 4, ensure_ascii = False))

            # 打印日志
            message = Localizer.get().file_checker_kana_full.replace("{COUNT}", f"{count}")
            message = message.replace("{PERCENT}", f"{(count / (len(self.items_translated) + len(self.items_untranslated)) * 100):.2f}")
            message = message.replace("{TARGET}", f"{Localizer.get().path_result_check_kana}")
            self.info(message)

    # 谚文残留检查
    def check_hangeul(self) -> None:
        if self.config.source_language != BaseLanguage.Enum.KO:
            return None

        count = 0
        result: dict[str, str] = {}

        for item in self.items_translated:
            if TextHelper.KO.any_hangeul(item.get_dst()):
                count = count + 1
                result.setdefault(item.get_file_path(), {})[item.get_src()] = item.get_dst()

        if count == 0:
            self.info(Localizer.get().file_checker_hangeul)
        else:
            target = f"{self.config.output_folder}/{Localizer.get().path_result_check_hangeul}".replace("\\", "/")
            self.info(
                Localizer.get().file_checker_hangeul_full.replace("{COUNT}", f"{count}")
                                                         .replace("{PERCENT}", f"{(count / (len(self.items_translated) + len(self.items_untranslated)) * 100):.2f}")
                                                         .replace("{TARGET}", f"{Localizer.get().path_result_check_hangeul}")
            )
            with open(target, "w", encoding = "utf-8") as writer:
                writer.write(json.dumps(result, indent = 4, ensure_ascii = False))

    # 文本保护检查
    def check_text_preserve(self) -> None:
        count = 0
        result: dict[str, str] = {
            Localizer.get().file_checker_text_preserve_alert_key: Localizer.get().file_checker_text_preserve_alert_value,
        }

        for i, (item, src_repl, dst_repl) in enumerate(zip(self.items_translated, self.src_repls, self.dst_repls)):
            if i % 2000 == 0:
                time.sleep(0)
            if self.text_processor.check(src_repl, dst_repl, item.get_text_type()) == False:
                count = count + 1
                result.setdefault(item.get_file_path(), {})[item.get_src()] = item.get_dst()

        if count == 0:
            self.info(Localizer.get().file_checker_text_preserve)
        else:
            target = f"{self.config.output_folder}/{Localizer.get().path_result_check_text_preserve}".replace("\\", "/")
            with open(target, "w", encoding = "utf-8") as writer:
                writer.write(json.dumps(result, indent = 4, ensure_ascii = False))

            # 打印日志
            message = Localizer.get().file_checker_text_preserve_full.replace("{COUNT}", f"{count}")
            message = message.replace("{PERCENT}", f"{(count / (len(self.items_translated) + len(self.items_untranslated)) * 100):.2f}")
            message = message.replace("{TARGET}", f"{Localizer.get().path_result_check_text_preserve}")
            self.info(message)

    # 相似度较高检查
    def check_similarity(self) -> None:
        count = 0
        result: dict[str, str] = {
            Localizer.get().file_checker_similarity_alert_key: Localizer.get().file_checker_similarity_alert_value,
        }

        for i, (item, src_repl, dst_repl) in enumerate(zip(self.items_translated, self.src_repls, self.dst_repls)):
            if i % 2000 == 0:
                time.sleep(0)
            src: str = src_repl.strip()
            dst: str = dst_repl.strip()

            # 判断是否包含或相似
            if src in dst or dst in src or TextHelper.check_similarity_by_jaccard(src, dst) > 0.80:
                count = count + 1
                result.setdefault(item.get_file_path(), {})[item.get_src()] = item.get_dst()

        if count == 0:
            self.info(Localizer.get().file_checker_similarity)
        else:
            target = f"{self.config.output_folder}/{Localizer.get().path_result_check_similarity}".replace("\\", "/")
            with open(target, "w", encoding = "utf-8") as writer:
                writer.write(json.dumps(result, indent = 4, ensure_ascii = False))

            # 打印日志
            message = Localizer.get().file_checker_similarity_full.replace("{COUNT}", f"{count}")
            message = message.replace("{PERCENT}", f"{(count / (len(self.items_translated) + len(self.items_untranslated)) * 100):.2f}")
            message = message.replace("{TARGET}", f"{Localizer.get().path_result_check_similarity}")
            self.info(message)

    # 术语表未生效检查（同时自动修复）
    def check_glossary(self) -> None:
        # 有效性检查
        if self.config.glossary_enable == False or len(self.config.glossary_data) == 0:
            return None

        # 如果启用了繁体输出，则先将数据转换为繁体
        if self.config.traditional_chinese_enable == True:
            self.config.glossary_data = [
                {
                    "src": v.get('src'),
                    "dst": ResultChecker.OPENCCS2T.convert(v.get('dst')),
                }
                for v in self.config.glossary_data
            ]
        else:
            self.config.glossary_data = [
                {
                    "src": v.get('src'),
                    "dst": ResultChecker.OPENCCT2S.convert(v.get('dst')),
                }
                for v in self.config.glossary_data
            ]

        count = 0
        fixed_count = 0
        result: dict[str, dict] = {}
        for i, (item, src_repl, dst_repl) in enumerate(zip(self.items_translated, self.src_repls, self.dst_repls)):
            if i % 2000 == 0:
                time.sleep(0)
            seen = set()
            current_dst = item.get_dst()
            fixed = False
            for v in self.config.glossary_data:
                glossary_src = v.get("src", "")
                glossary_dst = v.get("dst", "")
                # 如果原文包含术语，但译文没有正确翻译
                if glossary_src and glossary_dst and glossary_src in src_repl and glossary_dst not in current_dst:
                    # 自动替换：将原文术语替换为译文术语
                    if glossary_src in current_dst:
                        new_dst = current_dst.replace(glossary_src, glossary_dst)
                        item.set_dst(new_dst)
                        current_dst = new_dst
                        fixed = True
                        fixed_count += 1
                    else:
                        seen.add(item.get_src())
                        result.setdefault(f"{item.get_file_path()} | {glossary_src} -> {glossary_dst}", {})[item.get_src()] = item.get_dst()
            # 避免对同一条目重复计数
            count = count + len(seen)

        if fixed_count > 0:
            self.info(f"术语表自动修复：已自动替换 {fixed_count} 处未翻译的术语")

        if count == 0:
            self.info(Localizer.get().file_checker_glossary)
        else:
            target = f"{self.config.output_folder}/{Localizer.get().path_result_check_glossary}".replace("\\", "/")
            with open(target, "w", encoding = "utf-8") as writer:
                writer.write(json.dumps(result, indent = 4, ensure_ascii = False))

            # 打印日志
            message = Localizer.get().file_checker_glossary_full.replace("{COUNT}", f"{count}")
            message = message.replace("{PERCENT}", f"{(count / (len(self.items_translated) + len(self.items_untranslated)) * 100):.2f}")
            message = message.replace("{TARGET}", f"{Localizer.get().path_result_check_glossary}")
            self.info(message)

    # 英文+中文混合翻译错误检查
    # 检测类似 "It醒醒啦" "You我不知道" 这种翻译错误
    def check_mixed_translation(self) -> None:
        # 只对英文->中文的翻译进行检查
        if self.config.source_language != BaseLanguage.Enum.EN:
            return None
        if self.config.target_language != BaseLanguage.Enum.ZH:
            return None

        count = 0
        result: dict[str, dict] = {
            "说明": "以下译文可能存在翻译错误：英文单词未被翻译，直接拼接了中文译文",
        }

        for item in self.items_translated:
            dst = item.get_dst()
            # 按行检查每一行
            for line in dst.split("\n"):
                line = line.strip()
                if not line:
                    continue
                # 检测异常模式
                if self.RE_MIXED_TRANSLATION.search(line):
                    count += 1
                    result.setdefault(item.get_file_path(), {})[item.get_src()] = item.get_dst()
                    break  # 同一条目只计数一次

        if count == 0:
            self.info(Localizer.get().file_checker_mixed_translation)
        else:
            target = f"{self.config.output_folder}/{Localizer.get().path_result_check_mixed_translation}".replace("\\", "/")
            with open(target, "w", encoding = "utf-8") as writer:
                writer.write(json.dumps(result, indent = 4, ensure_ascii = False))

            # 打印日志
            message = Localizer.get().file_checker_mixed_translation_full.replace("{COUNT}", f"{count}")
            message = message.replace("{PERCENT}", f"{(count / (len(self.items_translated) + len(self.items_untranslated)) * 100):.2f}")
            message = message.replace("{TARGET}", f"{Localizer.get().path_result_check_mixed_translation}")
            self.info(message)

    # 未翻译检查
    def check_untranslated(self) -> None:
        count = 0
        result: dict[str, str] = {}

        for item in self.items_untranslated:
            count = count + 1
            result.setdefault(item.get_file_path(), {})[item.get_src()] = item.get_dst()

        if count == 0:
            pass
        else:
            target = f"{self.config.output_folder}/{Localizer.get().path_result_check_untranslated}".replace("\\", "/")
            with open(target, "w", encoding = "utf-8") as writer:
                writer.write(json.dumps(result, indent = 4, ensure_ascii = False))

    # 重试次数达到阈值检查
    def check_retry_count_threshold(self) -> None:
        if self.config.result_checker_retry_count_threshold != True:
            return None

        count = 0
        result: dict[str, str] = {}

        for item in [v for v in self.items_translated if v.get_retry_count() >= ResponseChecker.RETRY_COUNT_THRESHOLD]:
            count = count + 1
            result.setdefault(item.get_file_path(), {})[item.get_src()] = item.get_dst()

        if count == 0:
            pass
        else:
            target = f"{self.config.output_folder}/{Localizer.get().path_result_check_retry_count_threshold}".replace("\\", "/")
            with open(target, "w", encoding = "utf-8") as writer:
                writer.write(json.dumps(result, indent = 4, ensure_ascii = False))
