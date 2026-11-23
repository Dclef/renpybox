"""子进程 stdout 字节解码：兼容 UTF-8（Python runner）与 GBK/GB18030（Windows JDK keytool）。"""

from __future__ import annotations


def decode_process_output(raw: bytes) -> str:
    """按 UTF-8 → GBK → GB18030 → UTF-8(replace) 解码一段完整行字节。"""
    if not raw:
        return ""
    data = raw
    # 去掉 UTF-8 BOM，避免把 BOM 当正文
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    for encoding in ("gbk", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    # 全失败时用替换符，不静默丢弃字节
    return data.decode("utf-8", errors="replace")