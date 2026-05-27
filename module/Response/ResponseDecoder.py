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
    4. 编号文本: 1. 译文 / 1: 译文
    """
    
    # Markdown 代码块正则
    RE_MARKDOWN_FENCE = re.compile(r"```(?:json|jsonline)?\s*\n?(.*?)\n?```", re.DOTALL | re.IGNORECASE)
    
    # 编号文本正则 (1. / 1: / 1： / 【1】/ [1])
    RE_NUMBERED_LINE = re.compile(r"^(?:(\d+)[\.\:：\】\]]|\【(\d+)\】|\[(\d+)\])\s*(.+)$", re.MULTILINE)

    def __init__(self) -> None:
        super().__init__()
        # 兼容旧调用方；新代码应使用 decode_result() 返回的 method。
        self.last_method: str = ""

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
        self.last_method = ""

        # 0. 结构化输出优先解析 {"translations": [...]}
        if structured:
            dsts = self._parse_structured(response)
            if self._validate_count(dsts, expected_count, "STRUCTURED"):
                return self._make_result(dsts, glossarys, "STRUCTURED")
        
        # 1. 标准 JSONLINE 解析
        dsts, glossarys = self._parse_jsonline(response)
        if self._validate_count(dsts, expected_count, "JSONLINE"):
            return self._make_result(dsts, glossarys, "JSONLINE")
        
        # 2. 去掉 Markdown 围栏后重试
        cleaned = self._strip_markdown_fence(response)
        if cleaned != response:
            dsts, glossarys = self._parse_jsonline(cleaned)
            if self._validate_count(dsts, expected_count, "Markdown-JSONLINE"):
                return self._make_result(dsts, glossarys, "MARKDOWN_JSONLINE")

        # 3. 单一 JSON 字典
        target_text = cleaned if cleaned != response else response
        dsts = self._parse_json_dict(target_text)
        if self._validate_count(dsts, expected_count, "JSON-Dict"):
            return self._make_result(dsts, glossarys, "JSON_DICT")

        # 4. 编号文本（可选，用于某些模型不遵守格式时）
        dsts = self._parse_numbered_text(response)
        if self._validate_count(dsts, expected_count, "Numbered-Text"):
            self.warning(f"[DECODE] 使用编号文本解析（非标准格式）")
            return self._make_result(dsts, glossarys, "NUMBERED_TEXT")

        # 5. 单行纯文本兜底：适合小模型只返回译文正文的情况
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
        """创建解析结果，并同步旧的 last_method 字段。"""
        self.last_method = method
        return ResponseDecodeResult(dsts, glossarys, method)

    def _parse_structured(self, text: str) -> list[str]:
        """解析结构化输出 {"translations": [...]}"""
        try:
            cleaned = self._strip_markdown_fence(text)
            json_data = repair.loads(cleaned)
            if isinstance(json_data, dict):
                translations = json_data.get("translations")
                if isinstance(translations, list):
                    return [str(item) for item in translations]
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
            try:
                json_data = repair.loads(line)
                if isinstance(json_data, dict):
                    # 翻译结果 (单键值对)
                    if len(json_data) == 1:
                        _, v = list(json_data.items())[0]
                        if isinstance(v, str):
                            dsts.append(v)
                    # 术语表条目 (三键值对)
                    elif len(json_data) == 3 and all(k in json_data for k in ("src", "dst", "gender")):
                        glossarys.append({
                            "src": str(json_data.get("src", "")),
                            "dst": str(json_data.get("dst", "")),
                            "info": str(json_data.get("gender", "")),
                        })
            except Exception:
                pass
        return dsts, glossarys
    
    def _parse_json_dict(self, text: str) -> list[str]:
        """单一 JSON 字典解析，按键排序"""
        try:
            json_data = repair.loads(text)
            if isinstance(json_data, dict):
                # 尝试按数字键排序
                try:
                    sorted_items = sorted(json_data.items(), key=lambda x: int(x[0]) if str(x[0]).isdigit() else float('inf'))
                except (ValueError, TypeError):
                    sorted_items = list(json_data.items())
                return [str(v) for k, v in sorted_items if isinstance(v, str)]
        except Exception:
            pass
        return []
    
    def _strip_markdown_fence(self, text: str) -> str:
        """去除 Markdown 代码围栏"""
        match = self.RE_MARKDOWN_FENCE.search(text)
        if match:
            return match.group(1).strip()
        return text
    
    def _parse_numbered_text(self, text: str) -> list[str]:
        """解析编号文本格式 (1. 译文 / 1: 译文 / 【1】译文)"""
        results = []
        for match in self.RE_NUMBERED_LINE.finditer(text):
            # 提取编号和内容
            num = match.group(1) or match.group(2) or match.group(3)
            content = match.group(4).strip()
            if content:
                results.append((int(num), content))
        
        # 按编号排序
        results.sort(key=lambda x: x[0])
        return [content for _, content in results]

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
        if candidate.startswith("{") and candidate.endswith("}"):
            return ""
        if candidate.startswith("[") and candidate.endswith("]"):
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
