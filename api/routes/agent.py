"""复用现有 AgentService，网页和 Electron 共用一份会话。"""

from fastapi import APIRouter, HTTPException, Request

from api.routes.settings import _sanitise
from api.schemas import AgentConfirmationRequest, AgentMessageRequest

router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.get("")
def read_session(request: Request) -> dict:
    return _sanitise(request.app.state.agent.snapshot())


@router.post("/message")
def send_message(request: Request, body: AgentMessageRequest) -> dict:
    config = request.app.state.config
    platform = config.get_platform(config.agent_platform)
    if not isinstance(platform, dict):
        raise HTTPException(status_code=400, detail="请先在 Agent 页选择接口；没有可用接口时请前往接口管理添加")
    if str(platform.get("api_format", "")).casefold() not in {"openai", "anthropic", "google"}:
        raise HTTPException(status_code=400, detail="Agent 需要支持工具调用的 OpenAI、Anthropic 或 Google 接口，不能使用机器翻译或 SakuraLLM 接口")
    try:
        return _sanitise(request.app.state.agent.start(body.message, body.thinking_level))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/stop")
def stop_session(request: Request) -> dict:
    return _sanitise(request.app.state.agent.cancel())


@router.post("/reset")
def reset_session(request: Request) -> dict:
    try:
        return _sanitise(request.app.state.agent.reset())
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/confirm")
def confirm_tool(request: Request, body: AgentConfirmationRequest) -> dict:
    try:
        return _sanitise(request.app.state.agent.confirm(body.confirmation_id, body.approved))
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
