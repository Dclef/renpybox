"""桌面端共用的模型列表查询，不依赖 Qt。"""
import json
import urllib.error
import urllib.request

from base.Base import Base


def list_models(api_url: str, api_key: str, api_format: str) -> list[str]:
    if api_format in Base.MACHINE_API_FORMATS:
        return ["free"]
    if api_format == Base.APIFormat.GOOGLE:
        from google import genai
        with genai.Client(api_key=api_key, http_options={"timeout": 30000}) as client:
            result = [model.name for model in client.models.list()]
    elif api_format == Base.APIFormat.ANTHROPIC:
        import anthropic
        with anthropic.Anthropic(api_key=api_key, base_url=api_url, timeout=30, max_retries=0) as client:
            models = client.models.list()
            result = [getattr(model, "id", "") for model in getattr(models, "data", models)]
    else:
        import openai
        with openai.OpenAI(api_key=api_key or "no-key-required", base_url=api_url, timeout=30, max_retries=0) as client:
            models = client.models.list()
            result = [getattr(model, "id", "") for model in getattr(models, "data", models)]
    return sorted({model for model in result if isinstance(model, str) and model.strip()})


def _first_int(payload: dict, names: tuple[str, ...]) -> int:
    for name in names:
        value = payload.get(name)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)) and int(value) > 0:
            return int(value)
    return 0


def list_model_capabilities(
    api_url: str,
    api_key: str,
    api_format: str,
) -> dict[str, tuple[int, int]]:
    """从供应商的 /models 接口读取每个模型的 (上下文窗口, 最大输出)。

    目录是**运行时**取的，所以不必在本项目里维护一张会过期的模型表：
    - Google 的 Model 自带 ``input_token_limit`` / ``output_token_limit``；
    - OpenRouter 一类的 OpenAI 兼容目录会带 ``context_length`` 与
      ``top_provider.max_completion_tokens``；
    - 只返回 id 的供应商（OpenAI 原厂）拿不到容量，返回空，由调用方兜底。

    任何网络或解析失败都返回空字典，绝不因为查目录失败挡住翻译。
    """

    if api_format in Base.MACHINE_API_FORMATS:
        return {}

    if api_format == Base.APIFormat.GOOGLE:
        try:
            from google import genai

            result: dict[str, tuple[int, int]] = {}
            with genai.Client(api_key=api_key, http_options={"timeout": 15000}) as client:
                for model in client.models.list():
                    name = str(getattr(model, "name", "") or "").split("/")[-1]
                    context_window = int(getattr(model, "input_token_limit", 0) or 0)
                    max_output = int(getattr(model, "output_token_limit", 0) or 0)
                    if name and (context_window or max_output):
                        result[name] = (context_window, max_output)
            return result
        except Exception:  # noqa: BLE001 - 查目录失败不允许影响主流程
            return {}

    if api_format == Base.APIFormat.ANTHROPIC:
        # Anthropic 的模型列表不带上下文与输出上限，交给兜底。
        return {}

    url = f"{str(api_url or '').rstrip('/')}/models"
    request = urllib.request.Request(url, method="GET")
    if api_key:
        request.add_header("Authorization", f"Bearer {api_key}")
    request.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, OSError, ValueError):
        return {}

    entries = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(entries, list):
        return {}

    catalog: dict[str, tuple[int, int]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        model_id = entry.get("id") or entry.get("name")
        if not isinstance(model_id, str) or not model_id.strip():
            continue
        context_window = _first_int(
            entry,
            ("context_length", "context_window", "max_context_length", "max_input_tokens"),
        )
        max_output = _first_int(
            entry,
            (
                "max_completion_tokens",
                "max_output_tokens",
                "max_tokens",
                "top_provider_max_completion_tokens",
            ),
        )
        top_provider = entry.get("top_provider")
        if not max_output and isinstance(top_provider, dict):
            max_output = _first_int(
                top_provider,
                ("max_completion_tokens", "max_output_tokens"),
            )
        if context_window or max_output:
            catalog[model_id.strip()] = (context_window, max_output)
    return catalog


__all__ = ["list_models", "list_model_capabilities"]
