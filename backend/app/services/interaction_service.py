from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.orm import (
    HCP, Product, Interaction, InteractionProduct, SampleDrop, MaterialShared,
    InteractionStatus, EntryMode, FollowUp,
)

# Interaction columns an edit is allowed to touch. Deliberately excludes id,
# hcp_id, rep_id, entry_mode, source_transcript, created_at — identity and
# provenance fields aren't "editable data", they're the record's history.
EDITABLE_INTERACTION_FIELDS = {
    "interaction_type",
    "interaction_datetime",
    "duration_minutes",
    "channel_location",
    "key_message_notes",
    "hcp_sentiment",
    "interest_level",
    "follow_up_required",
    "follow_up_action",
    "follow_up_due_date",
}


def _get_or_create_product(db: Session, name: str) -> Product:
    product = db.query(Product).filter(Product.name.ilike(name)).first()
    if not product:
        product = Product(name=name)
        db.add(product)
        db.flush()
    return product


def _find_hcp_by_name(db: Session, hcp_name: str) -> Optional[HCP]:
    """Read-only lookup — unlike _resolve_hcp, never creates a stub record."""
    parts = hcp_name.strip().split(" ", 1)
    first, last = (parts[0], parts[1] if len(parts) > 1 else "")
    query = db.query(HCP).filter(HCP.first_name.ilike(f"%{first}%"))
    if last:
        query = query.filter(HCP.last_name.ilike(f"%{last}%"))
    return query.first()


def _resolve_hcp(db: Session, hcp_id: str | None, hcp_name: str | None) -> HCP:
    if hcp_id:
        hcp = db.query(HCP).get(hcp_id)
        if hcp:
            return hcp
    if hcp_name:
        parts = hcp_name.strip().split(" ", 1)
        first, last = (parts[0], parts[1] if len(parts) > 1 else "")
        hcp = db.query(HCP).filter(HCP.first_name.ilike(first), HCP.last_name.ilike(last)).first()
        if hcp:
            return hcp
        # Unknown HCP mentioned in chat -> create a lightweight stub record for
        # a data-steward to reconcile/merge later, rather than blocking the save.
        hcp = HCP(first_name=first, last_name=last or "(unspecified)")
        db.add(hcp)
        db.flush()
        return hcp
    raise ValueError("Either hcp_id or hcp_name is required to log an interaction.")


def create_interaction(
    db: Session,
    rep_id: str,
    payload: Dict[str, Any],
    entry_mode: EntryMode,
    compliance_flags: list[str] | None = None,
    source_transcript: str | None = None,
    ai_confidence_score: float | None = None,
) -> Interaction:
    hcp = _resolve_hcp(db, payload.get("hcp_id"), payload.get("hcp_name"))

    status = InteractionStatus.PENDING_REVIEW if compliance_flags else InteractionStatus.SUBMITTED

    interaction_datetime = payload.get("interaction_datetime")
    if isinstance(interaction_datetime, str):
        interaction_datetime = datetime.fromisoformat(interaction_datetime)

    interaction = Interaction(
        hcp_id=hcp.id,
        rep_id=rep_id,
        interaction_type=payload["interaction_type"],
        interaction_datetime=interaction_datetime,
        duration_minutes=payload.get("duration_minutes"),
        channel_location=payload.get("channel_location"),
        key_message_notes=payload.get("key_message_notes"),
        hcp_sentiment=payload.get("hcp_sentiment"),
        interest_level=payload.get("interest_level"),
        follow_up_required=payload.get("follow_up_required", False),
        follow_up_action=payload.get("follow_up_action"),
        follow_up_due_date=payload.get("follow_up_due_date"),
        entry_mode=entry_mode,
        status=status,
        compliance_flags=compliance_flags or [],
        source_transcript=source_transcript,
        ai_confidence_score=ai_confidence_score,
    )
    db.add(interaction)
    db.flush()

    for p in payload.get("products_discussed", []) or []:
        product = _get_or_create_product(db, p["product_name"])
        db.add(InteractionProduct(
            interaction_id=interaction.id,
            product_id=product.id,
            detailing_sequence=p.get("detailing_sequence"),
            reaction_notes=p.get("reaction_notes"),
        ))

    for s in payload.get("samples_dropped", []) or []:
        product = _get_or_create_product(db, s["product_name"])
        db.add(SampleDrop(
            interaction_id=interaction.id,
            product_id=product.id,
            quantity=s["quantity"],
            lot_number=s.get("lot_number"),
            hcp_signature_captured=s.get("hcp_signature_captured", False),
        ))

    for m in payload.get("materials_shared", []) or []:
        db.add(MaterialShared(
            interaction_id=interaction.id,
            material_name=m["material_name"],
            material_type=m.get("material_type"),
        ))

    db.commit()
    db.refresh(interaction)
    return interaction


def update_interaction(
    db: Session,
    interaction_id: str,
    updates: Dict[str, Any],
    compliance_flags: Optional[List[str]] = None,
) -> Interaction:
    """The single write path for the Edit Interaction tool/endpoint. Applies a
    whitelisted set of field changes to an already-logged interaction; re-runs the
    same PENDING_REVIEW gating create_interaction uses if the edit introduces (or
    clears) compliance flags, so an edited record can't silently skip MLR review.
    """
    interaction = db.query(Interaction).get(interaction_id)
    if not interaction:
        raise ValueError(f"No interaction found with id {interaction_id}")

    for field, value in updates.items():
        if field not in EDITABLE_INTERACTION_FIELDS:
            continue
        if field in ("interaction_datetime", "follow_up_due_date") and isinstance(value, str):
            value = datetime.fromisoformat(value)
        setattr(interaction, field, value)

    if compliance_flags is not None:
        interaction.compliance_flags = compliance_flags
        interaction.status = InteractionStatus.PENDING_REVIEW if compliance_flags else InteractionStatus.SUBMITTED

    interaction.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(interaction)
    return interaction


def get_hcp_recent_interactions(db: Session, hcp_name: str, limit: int = 3) -> List[Interaction]:
    hcp = _find_hcp_by_name(db, hcp_name)
    if not hcp:
        return []
    return (
        db.query(Interaction)
        .filter(Interaction.hcp_id == hcp.id)
        .order_by(Interaction.interaction_datetime.desc())
        .limit(limit)
        .all()
    )


def list_recent_interactions(db: Session, rep_id: str, limit: int = 20) -> List[Interaction]:
    return (
        db.query(Interaction)
        .filter(Interaction.rep_id == rep_id)
        .order_by(Interaction.created_at.desc())
        .limit(limit)
        .all()
    )


def get_most_recent_interaction_id(db: Session, rep_id: str) -> Optional[str]:
    interaction = (
        db.query(Interaction)
        .filter(Interaction.rep_id == rep_id)
        .order_by(Interaction.created_at.desc())
        .first()
    )
    return interaction.id if interaction else None


def create_follow_up(
    db: Session,
    rep_id: str,
    hcp_name: str,
    action: str,
    due_date: Optional[str] = None,
    interaction_id: Optional[str] = None,
) -> FollowUp:
    hcp = _resolve_hcp(db, None, hcp_name)
    follow_up = FollowUp(
        hcp_id=hcp.id,
        rep_id=rep_id,
        interaction_id=interaction_id,
        action=action,
        due_date=datetime.fromisoformat(due_date) if isinstance(due_date, str) else due_date,
    )
    db.add(follow_up)
    db.commit()
    db.refresh(follow_up)
    return follow_up
