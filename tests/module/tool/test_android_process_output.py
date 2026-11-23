from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest

from module.Tool.androidProcessOutput import decode_process_output
from module.Tool.AndroidBuilder import AndroidBuilder


def test_ascii_passthrough() -> None:
    raw = b"Generating 2,048 bit RSA key pair\n".strip()
    assert decode_process_output(raw) == "Generating 2,048 bit RSA key pair"


def test_utf8_chinese_strict() -> None:
    text = "正在为 2,048 位 RSA 密钥对生成自签名证书"
    raw = text.encode("utf-8")
    assert decode_process_output(raw) == text


def test_gbk_chinese_from_keytool_style() -> None:
    text = "正在生成 2,048 位 RSA 密钥"
    raw = text.encode("gbk")
    decoded = decode_process_output(raw)
    assert "正在生成" in decoded
    assert "2,048" in decoded
    assert "RSA" in decoded
    assert "\u0370" not in decoded  # 常见 GBK 误按 UTF-8 读出的乱码块


def test_gb18030_specific_sequence() -> None:
    text = "𠮷野家"
    raw = text.encode("gb18030")
    assert decode_process_output(raw) == text


def test_invalid_bytes_fallback_replace() -> None:
    raw = b"\xff\xfe\xfd"
    result = decode_process_output(raw)
    assert isinstance(result, str)
    assert "\ufffd" in result


def test_mixed_encoding_lines_independently() -> None:
    en = b"Done"
    utf8 = "已写入".encode("utf-8")
    gbk = "正在生成签名".encode("gbk")
    assert decode_process_output(en) == "Done"
    assert decode_process_output(utf8) == "已写入"
    assert decode_process_output(gbk) == "正在生成签名"


def test_utf8_bom_stripped() -> None:
    text = "hello"
    raw = b"\xef\xbb\xbf" + text.encode("utf-8")
    assert decode_process_output(raw) == text


class _FakeBinaryStdout:
    def __init__(self, lines: list[bytes]) -> None:
        self._lines = [line if line.endswith(b"\n") else line + b"\n" for line in lines]

    def __iter__(self):
        yield from self._lines


def test_run_process_feeds_decoded_gbk_to_callback(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    gbk_line = "正在为 2,048 位 RSA 密钥对生成自签名证书".encode("gbk")
    captured: list[str] = []

    def fake_popen(*_args, **_kwargs):
        return SimpleNamespace(stdout=_FakeBinaryStdout([gbk_line, b"English ok"]), wait=lambda: 0)

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    builder = AndroidBuilder(str(tmp_path), str(tmp_path))
    code = builder._run_process(["echo"], on_output=captured.append)

    assert code == 0
    assert "正在为" in captured[0]
    assert "RSA" in captured[0]
    assert captured[1] == "English ok"