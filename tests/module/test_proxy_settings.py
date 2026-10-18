"""网络代理解析：开关 + 地址 → 直连 / 指定代理 / 跟随系统代理。"""

from __future__ import annotations

from types import SimpleNamespace

import httpx

from module.ProxySettings import (
    create_httpx_client,
    default_http_timeout,
    proxies_for_url,
    resolve_proxies,
    resolve_proxy_url,
    uses_system_proxy,
)


def cfg(enable, url=""):
    return SimpleNamespace(proxy_enable=enable, proxy_url=url)


def test_resolve_proxy_url_three_states():
    # 关闭 → 直连，即使填了地址也不用
    assert resolve_proxy_url(cfg(False, "http://127.0.0.1:7890")) is None
    # 打开 + 有地址 → 用地址
    assert resolve_proxy_url(cfg(True, " http://127.0.0.1:7890 ")) == "http://127.0.0.1:7890"
    # 打开 + 空地址 → None（由 trust_env 跟随系统代理）
    assert resolve_proxy_url(cfg(True, "")) is None
    assert resolve_proxy_url(cfg(True, "   ")) is None
    # 缺字段 / None 都要安全
    assert resolve_proxy_url(None) is None
    assert resolve_proxy_url(SimpleNamespace()) is None


def test_uses_system_proxy_only_when_enabled_and_empty():
    assert uses_system_proxy(cfg(True, "")) is True
    assert uses_system_proxy(cfg(True, "  ")) is True
    assert uses_system_proxy(cfg(True, "http://127.0.0.1:7890")) is False
    assert uses_system_proxy(cfg(False, "")) is False
    assert uses_system_proxy(None) is False


def test_resolve_proxies_shapes():
    assert resolve_proxies(cfg(True, "http://127.0.0.1:7890")) == {
        "http": "http://127.0.0.1:7890",
        "https": "http://127.0.0.1:7890",
    }
    assert resolve_proxies(cfg(True, "")) is None
    assert resolve_proxies(cfg(False, "http://x")) is None
    assert proxies_for_url(None) is None
    assert proxies_for_url("") is None
    assert proxies_for_url("http://a:1") == {"http": "http://a:1", "https": "http://a:1"}


def test_create_httpx_client_uses_proxy_kwarg_not_proxies():
    # httpx 0.28 已删除 proxies=，只能用 proxy=
    explicit = create_httpx_client("http://127.0.0.1:7890", default_http_timeout(5))
    try:
        assert isinstance(explicit, httpx.Client)
    finally:
        explicit.close()

    system = create_httpx_client(None, default_http_timeout(5), trust_env=True)
    try:
        assert isinstance(system, httpx.Client)
        assert system.trust_env is True
    finally:
        system.close()


def test_task_requester_client_respects_proxy(monkeypatch):
    """代理写进 httpx 客户端，并且切换代理会废弃旧连接。"""
    from module.Engine.TaskRequester import TaskRequester
    from base.Base import Base

    created = []

    real_create = create_httpx_client

    def spy(proxy_url, timeout=None, **kwargs):
        client = real_create(proxy_url, timeout, **kwargs)
        created.append((proxy_url, client))
        return client

    monkeypatch.setattr("module.Engine.TaskRequester.create_httpx_client", spy)
    monkeypatch.setattr(TaskRequester, "_last_proxy_url", "", raising=False)
    TaskRequester.close_all_clients()

    first = TaskRequester.get_client("https://api.test/v1", "k", Base.APIFormat.OPENAI, 30, proxy_url="http://127.0.0.1:7890")
    assert created[0][0] == "http://127.0.0.1:7890", "显式代理必须传给 httpx"
    # 同参数命中缓存，不重建
    again = TaskRequester.get_client("https://api.test/v1", "k", Base.APIFormat.OPENAI, 30, proxy_url="http://127.0.0.1:7890")
    assert again is first
    assert len(created) == 1

    # 换代理 → 重建（不复用旧连接）
    TaskRequester.get_client("https://api.test/v1", "k", Base.APIFormat.OPENAI, 30, proxy_url="http://127.0.0.1:1080")
    assert created[-1][0] == "http://127.0.0.1:1080"
    assert len(created) == 2

    TaskRequester.close_all_clients()
