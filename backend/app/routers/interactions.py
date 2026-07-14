from typing import List

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.interaction import InteractionCreate, InteractionOut, InteractionUpdate
from app.services import interaction_service
from app.models.orm import EntryMode, Interaction

router = APIRouter(prefix="/api/interactions", tags=["interactions"])


@router.post("", response_model=InteractionOut, status_code=201)
def create_interaction(
    payload: InteractionCreate,
    db: Session = Depends(get_db),
    x_rep_id: str = Header(..., description="Authenticated field rep's user id"),
):
    """Log an interaction submitted via the structured form."""
    try:
        interaction = interaction_service.create_interaction(
            db=db,
            rep_id=x_rep_id,
            payload=payload.model_dump(),
            entry_mode=EntryMode.STRUCTURED_FORM,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return interaction


@router.get("", response_model=List[InteractionOut])
def list_interactions(
    db: Session = Depends(get_db),
    x_rep_id: str = Header(..., description="Authenticated field rep's user id"),
    limit: int = 20,
):
    """Recent interactions for the current rep, most recently created first."""
    return interaction_service.list_recent_interactions(db, rep_id=x_rep_id, limit=limit)


@router.get("/{interaction_id}", response_model=InteractionOut)
def get_interaction(interaction_id: str, db: Session = Depends(get_db)):
    interaction = db.query(Interaction).get(interaction_id)
    if not interaction:
        raise HTTPException(status_code=404, detail="Interaction not found")
    return interaction


@router.patch("/{interaction_id}", response_model=InteractionOut)
def edit_interaction(interaction_id: str, payload: InteractionUpdate, db: Session = Depends(get_db)):
    """Edit an interaction submitted via the structured form — the same write path
    (`interaction_service.update_interaction`) the chat agent's edit_interaction
    tool uses, so both surfaces stay consistent.
    """
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update.")
    try:
        return interaction_service.update_interaction(db=db, interaction_id=interaction_id, updates=updates)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
