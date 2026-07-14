from typing import Annotated, Any, Dict, List, Optional, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


REQUIRED_FIELDS = [
    "hcp_name",
    "interaction_type",
    "interaction_datetime",
    "products_discussed",
    "key_message_notes",
]

# phrases that trigger a compliance / MLR (Medical-Legal-Regulatory) review flag
COMPLIANCE_TRIGGER_HINT = (
    "off-label use, unapproved indication, guaranteed outcomes, comparative "
    "superiority claims not on the approved label, pricing/rebate promises, "
    "or any promise made in exchange for prescribing"
)


class AgentState(TypedDict):
    session_id: str
    rep_id: str
    # LangGraph appends new messages to the checkpointed history via add_messages;
    # callers only need to pass the *new* message(s) on each turn, not full history.
    messages: Annotated[List[BaseMessage], add_messages]

    # Populated every turn by a lightweight extraction pass (gemma2-9b-it), purely to
    # drive the frontend's "Extraction Tray" UI — independent of what the tool-calling
    # agent below actually decides to do with the same information.
    extracted: Dict[str, Any]
    missing_fields: List[str]

    # Side effects of whichever tool(s) the agent invoked this turn.
    compliance_flags: List[str]
    last_saved_interaction_id: Optional[str]
    last_action: str  # NONE | LOGGED | EDITED | COMPLIANCE_CHECKED | HISTORY_LOOKED_UP | FOLLOW_UP_SCHEDULED

    # Guards against runaway tool-call loops within a single turn.
    tool_hops: int
