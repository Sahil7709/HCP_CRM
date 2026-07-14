# AI-First HCP CRM — Log Interaction Screen

A structured-form **and** conversational (LangGraph + Groq) way to log a field rep's
interaction with a Healthcare Professional, sharing one schema and one write path on
the backend.

See `docs/ARCHITECTURE.md` for the full design rationale.

```
hcp-crm/
├── backend/          FastAPI + LangGraph + Groq
│   ├── app/
│   │   ├── agent/        LangGraph graph, 5 tools, state, prompts, Groq client
│   │   ├── models/        SQLAlchemy ORM
│   │   ├── routers/       /api/interactions, /api/interactions/chat
│   │   ├── schemas/       Pydantic request/response models
│   │   └── services/      shared persistence logic (form + chat both call this)
│   ├── requirements.txt
│   └── .env.example
├── frontend/          React + Redux Toolkit
│   └── src/components/LogInteraction/
│       ├── LogInteractionScreen.jsx   mode toggle + layout
│       ├── StructuredForm.jsx
│       ├── ChatInterface.jsx
│       └── ExtractionTray.jsx         live "what the AI has captured" panel
├── db/schema.sql       Postgres DDL (mirrors the SQLAlchemy models)
└── docs/ARCHITECTURE.md
```

## Backend setup

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # add your Groq API key from console.groq.com/keys
                             # and point DATABASE_URL at your Postgres instance
uvicorn app.main:app --reload --port 8000
```

`create_all` runs on startup for local dev; `db/schema.sql` is the equivalent DDL for
a managed environment (wire up Alembic migrations for production).

## Frontend setup

```bash
cd frontend
npm install
npm run dev      # http://localhost:5173, proxies /api to localhost:8000
```

## API surface

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/interactions` | Save an interaction from the structured form. Requires `X-Rep-Id` header. |
| `GET` | `/api/interactions` | List the current rep's recent interactions. Requires `X-Rep-Id` header. |
| `GET` | `/api/interactions/{id}` | Fetch a saved interaction. |
| `PATCH` | `/api/interactions/{id}` | Edit a saved interaction (structured-form path). |
| `POST` | `/api/interactions/chat` | One turn of the conversational logger. Body: `{session_id, message, rep_id}`. |
| `GET` | `/health` | Liveness check. |

## LangGraph agent & tools

The chat surface is driven by a LangGraph agent (`backend/app/agent/graph.py`,
`llama-3.3-70b-versatile` bound to five tools via `bind_tools`) with five sales-activity
tools defined in `backend/app/agent/tools.py`:

1. **`log_interaction`** — save a new HCP interaction (LLM extracts fields from the chat,
   tightens long notes, and screens for MLR compliance before writing).
2. **`edit_interaction`** — modify a previously logged interaction ("actually, change the
   interest level to 5").
3. `check_compliance` — screen text for off-label / inducement language.
4. `get_hcp_history` — recall recent past interactions with a named HCP.
5. `schedule_follow_up` — capture a follow-up commitment tied to an HCP.

See `docs/ARCHITECTURE.md §5` for the full design write-up, including why each tool
exists and how it's demoed.
"# HCP_CRM" 
