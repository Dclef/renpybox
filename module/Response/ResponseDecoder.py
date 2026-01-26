import re
import json_repair as repair

from base.Base import Base

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

    def decode(self, response: str, expected_count: int = 0) -> tuple[list[str], list[dict[str, str]]]:
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
            return [], []
        
        dsts: list[str] = []
        glossarys: list[dict[str, str]] = []
        
        # 1. 标准 JSONLINE 解析
        dsts, glossarys = self._parse_jsonline(response)
        if self._validate_count(dsts, expected_count, "JSONLINE"):
            return dsts, glossarys
        
        # 2. 去掉 Markdown 围栏后重试
        cleaned = self._strip_markdown_fence(response)
        if cleaned != response:
            dsts, glossarys = self._parse_jsonline(cleaned)
            if self._validate_count(dsts, expected_count, "Markdown-JSONLINE"):
                return dsts, glossarys
        
        # 3. 单一 JSON 字典
        target_text = cleaned if cleaned != response else response
        dsts = self._parse_json_dict(target_text)
        if self._validate_count(dsts, expected_count, "JSON-Dict"):
            return dsts, glossarys
        
        # 4. 编号文本（可选，用于某些模型不遵守格式时）
        dsts = self._parse_numbered_text(response)
        if self._validate_count(dsts, expected_count, "Numbered-Text"):
            self.warning(f"[DECODE] 使用编号文本解析（非标准格式）")
            return dsts, glossarys
        
        # 全部失败，返回空
        preview = response[:200].replace('\n', '\\n') if len(response) > 200 else response.replace('\n', '\\n')
        self.warning(f"[DECODE] 所有解析方式均失败, 响应预览: {preview}")
        return [], glossarys
    
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
        elif len(dsts) > 0:
            self.debug(f"[DECODE] {method} 数量不匹配: {len(dsts)}/{expected} 行，继续尝试其他方式")
        return False