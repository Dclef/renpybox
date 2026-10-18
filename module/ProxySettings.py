"""网络代理设置的统一解析。

「网络代理」开关 + 地址的组合有三种含义：

    proxy_enable=False                   → 不使用代理（直连）
    proxy_enable=True, proxy_url 有地址   → 使用该地址
    proxy_enable=True, proxy_url 为空     → 跟随系统代理

第三种是用户明确要求的：Clash 之类工具打开「系统代理」后，应用里不必
再手抄一遍端口。httpx / requests / pygtrans 都通过 ``trust_env=True``
读取系统代理（Windows 下来自 Internet 选项，其它平台来自环境变量），
所以这里只需返回 ``None`` 并保留 trust_env 即可。
"""

from __future__ import annotations

from typing import Any, Optional


def resolve_proxy_url(config: Any) -> Optional[str]:
    """返回需要显式使用的代理地址；None 表示直连或跟随系统代理。"""
    if config is None:
        return None
    if getattr(config, "proxy_enable", False) is not True:
        return None
    url = getattr(config, "proxy_url", "") or getattr(config, "proxy", "") or ""
    if not isinstance(url, str):
        return None
    url = url.strip()
    return url or None


def uses_system_proxy(config: Any) -> bool:
    """开关打开但地址留空时，表示跟随系统代理。"""
    if config is None:
        return False
    if getattr(config, "proxy_enable", False) is not True:
        return False
    url = getattr(config, "proxy_url", "") or getattr(config, "proxy", "") or ""
    return not (isinstance(url, str) and url.strip())


def resolve_proxies(config: Any) -> Optional[dict[str, str]]:
    """给 requests / pygtrans 用的 ``proxies`` 参数。"""
    return proxies_for_url(resolve_proxy_url(config))


def proxies_for_url(url: Optional[str]) -> Optional[dict[str, str]]:
    """已知代理地址时直接构造 ``proxies``；None / 空串返回 None。"""
    if not url or not isinstance(url, str):
        return None
    url = url.strip()
    if not url:
        return None
    return {"http": url, "https": url}


def create_httpx_client(proxy_url: Optional[str], timeout: Any = None, *, trust_env: bool = True) -> Any:
    """按代理地址创建 httpx.Client。

    httpx 0.28 起 ``proxies=`` 已被移除，只能传 ``proxy=``（单值）。
    ``proxy_url`` 为 None 时是否读系统代理仍由 ``trust_env`` 决定，所以
    「开关打开但地址留空 = 跟随系统代理」不需要额外分支。
    """
    import httpx

    kwargs: dict[str, Any] = {"trust_env": trust_env}
    if timeout is not None:
        kwargs["timeout"] = timeout
    if proxy_url:
        kwargs["proxy"] = proxy_url
    return httpx.Client(**kwargs)


def default_http_timeout(read_seconds: float) -> Any:
    """与 TaskRequester 里各处一致的四段超时。"""
    import httpx

    return httpx.Timeout(read=read_seconds, pool=8.00, write=8.00, connect=8.00)
