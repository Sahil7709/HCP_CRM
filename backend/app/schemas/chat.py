from typing import Optional, List, Dict, Any
from pydantic import BaseModel


class ChatTurnIn(BaseModel):
    session_id: str
    message: str
    rep_id: str


class ChatTurnOut(BaseModel):
    session_id: str
    reply: str
    stage: str  # EXTRACTING | CLARIFYING | COMPLIANCE_FLAGGED | CONFIRMING | SAVED
    extracted_fields: Dict[str, Any] = {}
    missing_fields: List[str] = []
    compliance_flags: List[str] = []
    interaction_id: Optional[str] = None
