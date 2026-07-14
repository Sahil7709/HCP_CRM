"""
The five sales-activity tools the LangGraph agent can call. Each tool opens its
own short-lived DB session (tools run inside the LangGraph node, outside FastAPI's
request-scoped `Depends(get_db)`), and every write goes through the *same*
`interaction_service` functions the structured-form REST endpoints use — so a
conversation logged/edited via chat and one submitted via the form produce
identical rows, not two divergent data models.

1. log_interaction   — persist a new HCP interaction.
2. edit_interaction   — modify a previously logged interaction.
3. check_compliance   — MLR/off-label screen a piece of text.
4. get_hcp_history    — recall recent past interactions with a named HCP.
5. schedule_follow_up — create a follow-up commitment tied to an HCP.
"""
import json
from typing import Any, Dict, List, Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.agent import groq_client
from app.agent.prompts import COMPLIANCE_SYSTEM_PROMPT
from app.database import SessionLocal
from app.models.orm import EntryMode
from app.services import interaction_service


def _to_plain(value: Any) -> Any:
    """StructuredTool validates nested list fields (products_discussed,
    samples_dropped) into their Pydantic sub-models (ProductArg, SampleArg) but
    doesn't recursively dump them back to dicts before calling the tool function
    — interaction_service does plain dict-style access (p["product_name"]), so
    normalize everything before it gets there.
    """
    if isinstance(value, BaseModel):
        return value.model_dump()
    if isinstance(value, list):
        return [_to_plain(v) for v in value]
    return value


def _screen_compliance(notes: str) -> Dict[str, Any]:
    if not notes or not notes.strip():
        return {"flags": [], "rationale": "No notes provided to screen."}
    raw = groq_client.reason(COMPLIANCE_SYSTEM_PROMPT, notes, json_mode=True)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {"flags": [], "rationale": "Compliance model returned an unparseable response."}
    return {"flags": parsed.get("flags", []), "rationale": parsed.get("rationale", "")}


def _tighten_notes(notes: str) -> str:
    """A small, genuinely-LLM step inside log_interaction: fast llama-3.1-8b-instant pass
    that condenses a rambling dictated note into 1-2 clean sentences before it's
    saved as the permanent call-report record. Left as-is if already concise.
    """
    if not notes or len(notes) < 220:
        return notes
    tightened = groq_client.reason(
        "Condense the following field-rep call note into 1-2 clear sentences. "
        "Preserve every specific fact (drug names, numbers, commitments). "
        "Return only the condensed text, no preamble.",
        notes,
    )
    return tightened.strip() or notes


class ProductArg(BaseModel):
    product_name: str
    reaction_notes: Optional[str] = None


class SampleArg(BaseModel):
    product_name: str
    quantity: int
    lot_number: Optional[str] = None


class LogInteractionArgs(BaseModel):
    hcp_name: str = Field(..., description="Full name of the HCP, e.g. 'Dr. Ananya Rao'")
    interaction_type: str = Field(
        ..., description="One of IN_PERSON_VISIT, VIRTUAL_MEETING, PHONE_CALL, EMAIL, CONFERENCE_BOOTH, SPEAKER_PROGRAM"
    )
    interaction_datetime: str = Field(..., description="ISO 8601 datetime, resolved against the reference date given in the system prompt")
    duration_minutes: Optional[int] = None
    channel_location: Optional[str] = Field(None, description="Clinic/hospital name, or 'virtual'")
    key_message_notes: str = Field(..., description="Summary of what was discussed with the HCP")
    hcp_sentiment: Optional[str] = Field(None, description="POSITIVE, NEUTRAL, or NEGATIVE")
    interest_level: Optional[int] = Field(None, description="1-5")
    products_discussed: List[ProductArg] = Field(default_factory=list)
    samples_dropped: List[SampleArg] = Field(default_factory=list)
    follow_up_required: bool = False
    follow_up_action: Optional[str] = None


class EditInteractionArgs(BaseModel):
    interaction_id: Optional[str] = Field(
        None, description="Id of the interaction to change. Omit to target the most recently logged interaction for this rep."
    )
    updates: Dict[str, Any] = Field(
        ...,
        description=(
            "Field -> new value. Editable fields: interaction_type, interaction_datetime, "
            "duration_minutes, channel_location, key_message_notes, hcp_sentiment, "
            "interest_level, follow_up_required, follow_up_action, follow_up_due_date."
        ),
    )


class CheckComplianceArgs(BaseModel):
    notes: str = Field(..., description="The text to screen for off-label, unsubstantiated, or inducement language")


class GetHcpHistoryArgs(BaseModel):
    hcp_name: str
    limit: int = Field(3, description="Max number of past interactions to return, most recent first")


class ScheduleFollowUpArgs(BaseModel):
    hcp_name: str
    action: str = Field(..., description="What needs to happen, e.g. 'Send updated efficacy data for Cardiozol'")
    due_date: Optional[str] = Field(None, description="ISO 8601 date/datetime this is due by")
    interaction_id: Optional[str] = Field(None, description="Interaction this follow-up was raised during, if any")


def build_tools(rep_id: str) -> List[StructuredTool]:
    """Fresh tool instances per chat turn, closing over the authenticated rep_id
    so the LLM never has to (and can't) supply it as an argument.
    """

    def _log_interaction(**kwargs) -> Dict[str, Any]:
        db = SessionLocal()
        try:
            kwargs = {k: _to_plain(v) for k, v in kwargs.items()}
            kwargs["key_message_notes"] = _tighten_notes(kwargs.get("key_message_notes", ""))
            compliance = _screen_compliance(kwargs.get("key_message_notes", ""))
            interaction = interaction_service.create_interaction(
                db=db,
                rep_id=rep_id,
                payload=kwargs,
                entry_mode=EntryMode.CONVERSATIONAL,
                compliance_flags=compliance["flags"],
                source_transcript=None,
                ai_confidence_score=0.9,
            )
            return {
                "status": "saved",
                "interaction_id": interaction.id,
                "record_status": interaction.status.value,
                "compliance_flags": compliance["flags"],
                "compliance_rationale": compliance["rationale"],
            }
        except Exception as e:  # noqa: BLE001 - surfaced back to the LLM as a tool result, not raised
            db.rollback()
            return {"status": "error", "error": str(e)}
        finally:
            db.close()

    def _edit_interaction(interaction_id: Optional[str], updates: Dict[str, Any]) -> Dict[str, Any]:
        db = SessionLocal()
        try:
            target_id = interaction_id or interaction_service.get_most_recent_interaction_id(db, rep_id)
            if not target_id:
                return {"status": "error", "error": "No interaction found to edit for this rep."}

            compliance_flags = None
            if "key_message_notes" in updates:
                compliance_flags = _screen_compliance(updates["key_message_notes"])["flags"]

            interaction = interaction_service.update_interaction(
                db=db, interaction_id=target_id, updates=updates, compliance_flags=compliance_flags,
            )
            return {
                "status": "updated",
                "interaction_id": interaction.id,
                "record_status": interaction.status.value,
                "compliance_flags": interaction.compliance_flags,
            }
        except Exception as e:  # noqa: BLE001
            db.rollback()
            return {"status": "error", "error": str(e)}
        finally:
            db.close()

    def _check_compliance(notes: str) -> Dict[str, Any]:
        return _screen_compliance(notes)

    def _get_hcp_history(hcp_name: str, limit: int = 3) -> Dict[str, Any]:
        db = SessionLocal()
        try:
            interactions = interaction_service.get_hcp_recent_interactions(db, hcp_name, limit)
            return {
                "status": "ok",
                "count": len(interactions),
                "interactions": [
                    {
                        "id": i.id,
                        "date": i.interaction_datetime.isoformat() if i.interaction_datetime else None,
                        "type": i.interaction_type.value if hasattr(i.interaction_type, "value") else i.interaction_type,
                        "notes": i.key_message_notes,
                        "sentiment": i.hcp_sentiment,
                        "products": [p.product.name for p in i.products_discussed],
                    }
                    for i in interactions
                ],
            }
        finally:
            db.close()

    def _schedule_follow_up(
        hcp_name: str, action: str, due_date: Optional[str] = None, interaction_id: Optional[str] = None
    ) -> Dict[str, Any]:
        db = SessionLocal()
        try:
            follow_up = interaction_service.create_follow_up(
                db=db, rep_id=rep_id, hcp_name=hcp_name, action=action, due_date=due_date, interaction_id=interaction_id,
            )
            return {"status": "scheduled", "follow_up_id": follow_up.id, "due_date": due_date}
        except Exception as e:  # noqa: BLE001
            db.rollback()
            return {"status": "error", "error": str(e)}
        finally:
            db.close()

    return [
        StructuredTool.from_function(
            func=_log_interaction,
            name="log_interaction",
            description=(
                "Save a new HCP interaction record. Call this once you have at least the HCP name, "
                "interaction type, date/time, products discussed, and a summary of the discussion. "
                "Automatically tightens long notes and screens them for MLR compliance issues before saving."
            ),
            args_schema=LogInteractionArgs,
        ),
        StructuredTool.from_function(
            func=_edit_interaction,
            name="edit_interaction",
            description=(
                "Modify one or more fields on an interaction that was already logged (this session or "
                "earlier). Use when the rep corrects or adds to something already saved."
            ),
            args_schema=EditInteractionArgs,
        ),
        StructuredTool.from_function(
            func=_check_compliance,
            name="check_compliance",
            description=(
                "Screen a piece of text for off-label claims, unapproved indications, unsubstantiated "
                "superiority claims, or inducement risk. Use before logging/editing notes that sound "
                "like they may need MLR review, or if the rep asks directly."
            ),
            args_schema=CheckComplianceArgs,
        ),
        StructuredTool.from_function(
            func=_get_hcp_history,
            name="get_hcp_history",
            description=(
                "Look up recent past interactions with a named HCP — use when the rep asks what was "
                "discussed last time, or when that context would help fill in the current log."
            ),
            args_schema=GetHcpHistoryArgs,
        ),
        StructuredTool.from_function(
            func=_schedule_follow_up,
            name="schedule_follow_up",
            description=(
                "Create a follow-up reminder/action tied to an HCP (and optionally a specific logged "
                "interaction) — e.g. 'send Dr. Rao the new efficacy data next week'."
            ),
            args_schema=ScheduleFollowUpArgs,
        ),
    ]
