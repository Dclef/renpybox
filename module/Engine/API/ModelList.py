"""桌面端共用的模型列表查询，不依赖 Qt。"""
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
