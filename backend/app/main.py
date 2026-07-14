from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, engine
from app.routers import interactions, chat

app = FastAPI(
    title="AI-First HCP CRM — Log Interaction API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(interactions.router)
app.include_router(chat.router)


@app.on_event("startup")
def on_startup():
    # In production this is handled by Alembic migrations (see db/schema.sql
    # for the equivalent DDL); create_all is convenient for local/dev use.
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health():
    return {"status": "ok"}
