import dataclasses
import re
import json_repair as repair

from base.Base import Base

@dataclasses.dataclass(frozen = True)
class ResponseDecodeResult:
    """模型回复解析结果。"""

    dsts: list[str]
    glossarys: list[dict[str, str]]
    method: str


class ResponseDecoder(Base):
    """
    响应解码器：将模型返回的文本解析为译文列表
    
    支持的格式（按优先级）：
    1. JSONLINE: {"0": "译文"}\n{"1": "译文"}
    2. Markdown代码块包裹的JSON
    3. 单一JSON字典: {"0": "译文", "1": "译文"}
    """
    
    # Markdown 代码块正则
    RE_MARKDOWN_FENCE = re.compile(r"```(?:json|jsonline)?\s*\n?(.*?)\n?```", re.DOTALL | re.IGNORECASE)
    TARGET_VALUE_KEYS: tuple[str, ...] = ("translation", "target", "dst", "content", "text", "value")
    NOISE_KEYS: frozenset[str] = frozenset((
        "index",
        "id",
        "no",
        "number",
        "line",
        "comment",
        "comments",
        "note",
        "notes",
        "src",
        "source",
        "original",
        "speaker",
        "role",
        "name",
        "gender",
        "glossary",
    ))

    def __init__(self) -> None:
        super().__init__()

    def decode(
        self,
        response: str,
        expected_count: int = 0,
        allow_plain_text_single: bool = False,
        structured: bool = False,
    ) -> tuple[list[str], list[dict[str, str]]]:
        result = self.decode_result(
            response,
            expected_count = expected_count,
            allow_plain_text_single = allow_plain_text_single,
            structured = structured,
        )
        return result.dsts, result.glossarys

    def decode_result(
        self,
        response: str,
        expected_count: int = 0,
        allow_plain_text_single: bool = False,
        structured: bool = False,
    ) -> ResponseDecodeResult:
        """
        解析响应文本，按优先级尝试多种格式
        
        Args:
            response: 模型返回的原始文本
            expected_count: 期望的译文行数，用于验证（0表示不验证）
            
        Returns:
            (译文列表, 术语表列表)
        """
        if not response or not isinstance(response, str):
            self.warning(f"[DECODE] 响应为空或类型错误: type={type(response)}")
            return self._make_result([], [], "FAIL")

        dsts: list[str] = []
        glossarys: list[dict[str, str]] = []
        cleaned = self._strip_markdown_fence(response)
        json_response = self._is_explicit_json_response(response, cleaned)

        # 0. 结构化输出优先解析 {"translations": [...]}
        if structured:
            dsts = self._parse_structured(cleaned)
            if self._validate_count(dsts, expected_count, "STRUCTURED"):
                return self._make_result(dsts, glossarys, "STRUCTURED")
        
        # 1. 标准 JSONLINE 解析
        dsts, glossarys = self._parse_jsonline(response)
        if self._validate_count(dsts, expected_count, "JSONLINE"):
            return self._make_result(dsts, glossarys, "JSONLINE")
        
        # 2. 去掉 Markdown 围栏后重试
        if cleaned != response:
            dsts, glossarys = self._parse_jsonline(cleaned)
            if self._validate_count(dsts, expected_count, "Markdown-JSONLINE"):
                return self._make_result(dsts, glossarys, "MARKDOWN_JSONLINE")

        # 3. 单一 JSON 字典
        target_text = cleaned if cleaned != response else response
        dsts = self._parse_json_dict(target_text)
        if self._validate_count(dsts, expected_count, "JSON-Dict"):
            return self._make_result(dsts, glossarys, "JSON_DICT")

        if json_response:
            self.warning("[DECODE] 检测到明确 JSON 响应，但未能提取有效译文，已阻断文本兜底解析")
            return self._make_result([], glossarys, "JSON_FAIL")

        # 4. 单行纯文本兜底：仅适合单行模式下小模型只返回译文正文的情况
        if expected_count == 1 and allow_plain_text_single == True:
            plain_text = self._parse_single_plain_text(cleaned if cleaned != response else response)
            if plain_text != "":
                self.debug(f"[DECODE] 使用单行纯文本兜底解析")
                return self._make_result([plain_text], glossarys, "PLAIN_TEXT")

        # 全部失败，返回空
        preview = response[:200].replace('\n', '\\n') if len(response) > 200 else response.replace('\n', '\\n')
        self.warning(f"[DECODE] 所有解析方式均失败, 响应预览: {preview}")
        return self._make_result([], glossarys, "FAIL")

    def _make_result(self, dsts: list[str], glossarys: list[dict[str, str]], method: str) -> ResponseDecodeResult:
        """创建解析结果。"""
        dsts = self._sanitize_nested_json_in_dsts(dsts)
        return ResponseDecodeResult(dsts, glossarys, method)

    # 某些模型（尤其 DeepSeek 不开思考时）会在 JSONLINE 值中嵌套输出
    # 完整的 JSON/dict 字符串，如 {"0": "{'index':1,'translation':'你好'}"}。
    # 解析后 dsts 中会残留 {'index':1,'translation':'你好'} 这类原始字符串。
    RE_NESTED_DICT_LIKE = re.compile(r"^\s*(?:\{.+\}|\[.+\])\s*$", re.DOTALL)

    def _sanitize_nested_json_in_dsts(self, dsts: list[str]) -> list[str]:
        """检测并清洗译文列表中残留的嵌套 JSON/dict 字符串。"""
        result: list[str] = []
        for dst in dsts:
            if not isinstance(dst, str):
                result.append(dst)
                continue
            stripped = dst.strip()
            if not self.RE_NESTED_DICT_LIKE.match(stripped):
                result.append(dst)
                continue
            if not self._is_explicit_json_response(stripped, stripped):
                result.append(dst)
                continue
            try:
                inner = repair.loads(stripped)
            except Exception:
                result.append(dst)
                continue
            if not isinstance(inner, (dict, list)):
                result.append(dst)
                continue

            translations = self._extract_json_translations(inner)
            if len(translations) > 0:
                result.append(translations[0])
            else:
                result.append("")
        return result

    def _parse_structured(self, text: str) -> list[str]:
        """解析结构化输出 {"translations": [...]}"""
        try:
            json_data = repair.loads(text)
            if isinstance(json_data, dict):
                translations = json_data.get("translations")
                if isinstance(translations, list):
                    return [
                        value if value is not None else ""
                        for value in (self._extract_translation_leaf(item) for item in translations)
                    ]
        except Exception:
            pass
        return []
    
    def _parse_jsonline(self, text: str) -> tuple[list[str], list[dict]]:
        """标准 JSONLINE 解析"""
        dsts = []
        glossarys = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if not self._is_explicit_json_response(line, line):
                continue
            try:
                json_data = repair.loads(line)
                if isinstance(json_data, dict):
                    # 术语表条目 (三键值对)
                    if len(json_data) == 3 and all(k in json_data for k in ("src", "dst", "gender")):
                        glossarys.append({
                            "src": str(json_data.get("src", "")),
                            "dst": str(json_data.get("dst", "")),
                            "info": str(json_data.get("gender", "")),
                        })
                        continue

                    translation = self._extract_translation_leaf(json_data)
                    if translation is not None:
                        dsts.append(translation)
            except Exception:
                pass
        return dsts, glossarys
    
    def _parse_json_dict(self, text: str) -> list[str]:
        """单一 JSON 字典解析，按键排序"""
        if not self._is_explicit_json_response(text, text):
            return []
        try:
            json_data = repair.loads(text)
            return self._extract_json_translations(json_data)
        except Exception:
            pass
        return []

    @classmethod
    def _extract_json_translations(cls, json_data) -> list[str]:
        if isinstance(json_data, dict):
            translations = json_data.get("translations")
            if isinstance(translations, list):
                return [
                    value if value is not None else ""
                    for value in (cls._extract_translation_leaf(item) for item in translations)
                ]

            numeric_items = [
                (int(str(k)), v)
                for k, v in json_data.items()
                if str(k).isdigit()
            ]
            if len(numeric_items) > 0 and len(numeric_items) == len(json_data):
                numeric_items.sort(key = lambda item: item[0])
                return [
                    value
                    for value in (cls._extract_translation_leaf(v) for _, v in numeric_items)
                    if value is not None
                ]

            leaf = cls._extract_translation_leaf(json_data)
            if leaf is not None:
                return [leaf]

        if isinstance(json_data, list):
            return [
                value if value is not None else ""
                for value in (cls._extract_translation_leaf(item) for item in json_data)
            ]

        return []

    @classmethod
    def _extract_translation_leaf(cls, value) -> str | None:
        if isinstance(value, str):
            return value
        if value is None:
            return ""
        if isinstance(value, (int, float, bool)):
            return str(value)
        if isinstance(value, list):
            if len(value) == 1:
                return cls._extract_translation_leaf(value[0])
            return None
        if not isinstance(value, dict):
            return None

        lowered = {str(k).lower(): k for k in value.keys()}
        for target_key in cls.TARGET_VALUE_KEYS:
            original_key = lowered.get(target_key)
            if original_key is not None:
                return cls._extract_translation_leaf(value.get(original_key))

        candidates = {
            k: v
            for k, v in value.items()
            if str(k).lower() not in cls.NOISE_KEYS
        }
        if len(candidates) == 1:
            _, candidate = next(iter(candidates.items()))
            return cls._extract_translation_leaf(candidate)

        if len(value) == 1:
            _, candidate = next(iter(value.items()))
            return cls._extract_translation_leaf(candidate)

        return None
    
    def _strip_markdown_fence(self, text: str) -> str:
        """去除 Markdown 代码围栏"""
        match = self.RE_MARKDOWN_FENCE.search(text)
        if match:
            return match.group(1).strip()
        return text

    def _is_explicit_json_response(self, text: str, cleaned: str) -> bool:
        """判断本次响应是否明确声明为 JSON，防止 JSON 失败后落入文本兜底。"""
        if not isinstance(text, str):
            return False

        if re.search(r"```(?:json|jsonline)", text, flags = re.IGNORECASE) is not None:
            return True

        candidate = cleaned.strip() if isinstance(cleaned, str) else text.strip()
        if candidate == "":
            return False

        if candidate.startswith("{"):
            inner = candidate[1:].lstrip()
            if not (
                inner.startswith(('"', "'"))
                or re.match(r"[A-Za-z_][A-Za-z0-9_-]*\s*:", inner) is not None
                or ":" in candidate
            ):
                return False
            return True

        if candidate.startswith("["):
            inner = candidate[1:].lstrip().lower()
            if not (
                inner.startswith(("{", "[", '"', "'", "]"))
                or re.match(r"-?\d", inner) is not None
                or inner.startswith(("true", "false", "null"))
            ):
                return False
            try:
                parsed = repair.loads(candidate)
            except Exception:
                return False
            return isinstance(parsed, (dict, list))

        try:
            parsed = repair.loads(candidate)
        except Exception:
            return False
        return isinstance(parsed, (dict, list))
    
    def _parse_single_plain_text(self, text: str) -> str:
        """解析单行纯文本兜底结果。"""
        if not isinstance(text, str):
            return ""

        lines = [line.strip() for line in text.splitlines() if line.strip() != ""]
        if lines == []:
            return ""

        candidate = lines[0]
        if len(lines) > 1:
            for line in lines:
                if re.match(r"^(译文|翻译|translation|translated)\s*[:：]\s*", line, flags = re.IGNORECASE):
                    candidate = re.sub(r"^(译文|翻译|translation|translated)\s*[:：]\s*", "", line, flags = re.IGNORECASE).strip()
                    break

        candidate = re.sub(r"^(译文|翻译|translation|translated)\s*[:：]\s*", "", candidate, flags = re.IGNORECASE).strip()
        candidate = candidate.strip().strip('"').strip("'").strip("`")
        if candidate == "":
            return ""

        # JSON 样式的输出不应走纯文本兜底，避免把错误的结构直接写回。
        if self._is_explicit_json_response(candidate, candidate):
            return ""

        return candidate
    
    def _validate_count(self, dsts: list, expected: int, method: str) -> bool:
        """验证解析结果数量"""
        if expected == 0:
            # 不验证数量，只要有结果就行
            if len(dsts) > 0:
                self.debug(f"[DECODE] {method} 解析成功: {len(dsts)} 行")
                return True
            return False

        if len(dsts) == expected:
            self.debug(f"[DECODE] {method} 解析成功: {len(dsts)}/{expected} 行")
            return True

        # 允许少量缺失（最多差2行且至少80%行数），补空行
        missing = expected - len(dsts)
        if 0 < missing <= 2 and len(dsts) >= expected * 0.8:
            self.warning(f"[DECODE] {method} 行数略少: {len(dsts)}/{expected}，补 {missing} 行空行")
            dsts.extend([""] * missing)
            return True

        if len(dsts) > 0:
            self.debug(f"[DECODE] {method} 数量不匹配: {len(dsts)}/{expected} 行，继续尝试其他方式")
        return False
