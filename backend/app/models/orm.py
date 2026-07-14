import uuid
import enum
from datetime import datetime

from sqlalchemy import (
    Column, String, Text, DateTime, Enum, ForeignKey, Numeric, Boolean, Integer
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.database import Base


def gen_uuid():
    return str(uuid.uuid4())


class InteractionType(str, enum.Enum):
    IN_PERSON_VISIT = "IN_PERSON_VISIT"
    VIRTUAL_MEETING = "VIRTUAL_MEETING"
    PHONE_CALL = "PHONE_CALL"
    EMAIL = "EMAIL"
    CONFERENCE_BOOTH = "CONFERENCE_BOOTH"
    SPEAKER_PROGRAM = "SPEAKER_PROGRAM"


class InteractionStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PENDING_REVIEW = "PENDING_REVIEW"   # flagged for MLR / compliance review
    SUBMITTED = "SUBMITTED"


class EntryMode(str, enum.Enum):
    STRUCTURED_FORM = "STRUCTURED_FORM"
    CONVERSATIONAL = "CONVERSATIONAL"


class FollowUpStatus(str, enum.Enum):
    OPEN = "OPEN"
    DONE = "DONE"


class HCP(Base):
    __tablename__ = "hcps"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    first_name = Column(String(120), nullable=False)
    last_name = Column(String(120), nullable=False)
    npi_number = Column(String(20), unique=True, index=True)  # National Provider Identifier
    specialty = Column(String(120))
    institution = Column(String(255))
    tier = Column(String(20))  # e.g. A / B / C targeting tier
    email = Column(String(255))
    phone = Column(String(50))

    interactions = relationship("Interaction", back_populates="hcp")

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"


class Product(Base):
    __tablename__ = "products"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    name = Column(String(255), nullable=False)
    brand_code = Column(String(50))
    is_sample_eligible = Column(Boolean, default=False)


class Interaction(Base):
    __tablename__ = "interactions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    hcp_id = Column(UUID(as_uuid=False), ForeignKey("hcps.id"), nullable=False)
    rep_id = Column(UUID(as_uuid=False), nullable=False)  # FK to field-rep/user table (owned by IAM module)

    interaction_type = Column(Enum(InteractionType), nullable=False)
    interaction_datetime = Column(DateTime, nullable=False)
    duration_minutes = Column(Integer)
    channel_location = Column(String(255))  # clinic name, virtual link, etc.

    key_message_notes = Column(Text)  # free-text discussion notes
    hcp_sentiment = Column(String(20))  # POSITIVE / NEUTRAL / NEGATIVE
    interest_level = Column(Integer)  # 1-5

    follow_up_required = Column(Boolean, default=False)
    follow_up_action = Column(Text)
    follow_up_due_date = Column(DateTime)

    entry_mode = Column(Enum(EntryMode), nullable=False, default=EntryMode.STRUCTURED_FORM)
    status = Column(Enum(InteractionStatus), nullable=False, default=InteractionStatus.DRAFT)
    compliance_flags = Column(JSONB, default=list)  # e.g. ["OFF_LABEL_MENTION"]

    # raw transcript retained for audit when logged conversationally
    source_transcript = Column(Text)
    ai_confidence_score = Column(Numeric(3, 2))  # 0.00 - 1.00, extraction confidence

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    hcp = relationship("HCP", back_populates="interactions")
    products_discussed = relationship("InteractionProduct", back_populates="interaction", cascade="all, delete-orphan")
    samples_dropped = relationship("SampleDrop", back_populates="interaction", cascade="all, delete-orphan")
    materials_shared = relationship("MaterialShared", back_populates="interaction", cascade="all, delete-orphan")

    @property
    def hcp_name(self) -> str | None:
        """Denormalized for InteractionOut, which speaks hcp_name rather than
        forcing every API consumer to resolve hcp_id via a second lookup.
        """
        return self.hcp.full_name if self.hcp else None


class InteractionProduct(Base):
    __tablename__ = "interaction_products"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    interaction_id = Column(UUID(as_uuid=False), ForeignKey("interactions.id"), nullable=False)
    product_id = Column(UUID(as_uuid=False), ForeignKey("products.id"), nullable=False)
    detailing_sequence = Column(Integer)  # order in which product was detailed
    reaction_notes = Column(Text)

    interaction = relationship("Interaction", back_populates="products_discussed")
    product = relationship("Product")

    @property
    def product_name(self) -> str | None:
        """Denormalized for the API response schema (InteractionOut), which
        speaks product_name rather than product_id — the rep never sees IDs.
        """
        return self.product.name if self.product else None


class SampleDrop(Base):
    __tablename__ = "sample_drops"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    interaction_id = Column(UUID(as_uuid=False), ForeignKey("interactions.id"), nullable=False)
    product_id = Column(UUID(as_uuid=False), ForeignKey("products.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    lot_number = Column(String(50))
    hcp_signature_captured = Column(Boolean, default=False)  # regulatory requirement (PDMA)

    interaction = relationship("Interaction", back_populates="samples_dropped")
    product = relationship("Product")

    @property
    def product_name(self) -> str | None:
        return self.product.name if self.product else None


class MaterialShared(Base):
    __tablename__ = "materials_shared"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    interaction_id = Column(UUID(as_uuid=False), ForeignKey("interactions.id"), nullable=False)
    material_name = Column(String(255), nullable=False)  # e.g. "Leave-behind: Efficacy Data Sheet v3"
    material_type = Column(String(50))  # LEAVE_BEHIND / E_DETAIL / BROCHURE

    interaction = relationship("Interaction", back_populates="materials_shared")


class FollowUp(Base):
    """A commitment made to (or about) an HCP that isn't itself an interaction —
    e.g. "send Dr. Rao the new efficacy data next week". Created by the
    schedule_follow_up LangGraph tool, optionally linked back to the interaction
    it was raised during.
    """
    __tablename__ = "follow_ups"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    hcp_id = Column(UUID(as_uuid=False), ForeignKey("hcps.id"), nullable=False)
    rep_id = Column(UUID(as_uuid=False), nullable=False)
    interaction_id = Column(UUID(as_uuid=False), ForeignKey("interactions.id"), nullable=True)

    action = Column(Text, nullable=False)
    due_date = Column(DateTime)
    status = Column(Enum(FollowUpStatus), nullable=False, default=FollowUpStatus.OPEN)

    created_at = Column(DateTime, default=datetime.utcnow)

    hcp = relationship("HCP")
    interaction = relationship("Interaction")
