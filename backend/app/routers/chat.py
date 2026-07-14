from fastapi import APIRouter

from langchain_core.messages import HumanMessage

from app.schemas.chat import ChatTurnIn, ChatTurnOut
from app.agent.graph import interaction_agent

router = APIRouter(prefix="/api/interactions/chat", tags=["interactions-chat"])

_STAGE_BY_ACTION = {
    "LOGGED": "SAVED",
    "EDITED": "EDITED",
}


@router.post("", response_model=ChatTurnOut)
def chat_turn(payload: ChatTurnIn):
    """
    One turn of the conversational "Log Interaction" flow. The LangGraph agent is
    checkpointed per session_id (MemorySaver), so only the new message needs to be
    sent each turn — prior turns are recalled automatically. Internally the agent
    may call any of its five tools (log_interaction, edit_interaction,
    check_compliance, get_hcp_history, schedule_follow_up) any number of times
    before replying; all of that happens inside this single call.
    """
    config = {"configurable": {"thread_id": payload.session_id}}

    result = interaction_agent.invoke(
        {
            "session_id": payload.session_id,
            "rep_id": payload.rep_id,
            "messages": [HumanMessage(content=payload.message)],
        },
        config=config,
    )

    return ChatTurnOut(
        session_id=payload.session_id,
        reply=result["messages"][-1].content,
        stage=_STAGE_BY_ACTION.get(result.get("last_action"), "CHATTING"),
        extracted_fields=result.get("extracted", {}),
        missing_fields=result.get("missing_fields", []),
        compliance_flags=result.get("compliance_flags", []),
        interaction_id=result.get("last_saved_interaction_id"),
    )
