from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, confloat


class ProductDiscussedIn(BaseModel):
    product_id: Optional[str] = None
    product_name: str
    detailing_sequence: Optional[int] = None
    reaction_notes: Optional[str] = None


class SampleDropIn(BaseModel):
    product_name: str
    quantity: int
    lot_number: Optional[str] = None
    hcp_signature_captured: bool = False


class MaterialSharedIn(BaseModel):
    material_name: str
    material_type: Optional[str] = None


class InteractionBase(BaseModel):
    hcp_id: Optional[str] = None
    hcp_name: Optional[str] = None  # allows lookup-by-name from chat mode
    interaction_type: str
    interaction_datetime: datetime
    duration_minutes: Optional[int] = None
    channel_location: Optional[str] = None
    key_message_notes: Optional[str] = None
    hcp_sentiment: Optional[str] = None
    interest_level: Optional[int] = Field(default=None, ge=1, le=5)
    follow_up_required: bool = False
    follow_up_action: Optional[str] = None
    follow_up_due_date: Optional[datetime] = None
    products_discussed: List[ProductDiscussedIn] = []
    samples_dropped: List[SampleDropIn] = []
    materials_shared: List[MaterialSharedIn] = []


class InteractionCreate(InteractionBase):
    entry_mode: str = "STRUCTURED_FORM"
    source_transcript: Optional[str] = None
    ai_confidence_score: Optional[confloat(ge=0, le=1)] = None
    compliance_flags: List[str] = []


class InteractionUpdate(BaseModel):
    """Edit Interaction payload — every field optional, only supplied ones change.
    Mirrors app.services.interaction_service.EDITABLE_INTERACTION_FIELDS.
    """
    interaction_type: Optional[str] = None
    interaction_datetime: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    channel_location: Optional[str] = None
    key_message_notes: Optional[str] = None
    hcp_sentiment: Optional[str] = None
    interest_level: Optional[int] = Field(default=None, ge=1, le=5)
    follow_up_required: Optional[bool] = None
    follow_up_action: Optional[str] = None
    follow_up_due_date: Optional[datetime] = None


class InteractionOut(InteractionBase):
    id: str
    rep_id: str
    status: str
    entry_mode: str
    compliance_flags: List[str] = []
    ai_confidence_score: Optional[float] = None
    created_at: datetime

    class Config:
        from_attributes = True
