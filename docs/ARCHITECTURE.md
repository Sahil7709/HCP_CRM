# AI-First HCP CRM — Log Interaction Screen

## 1. Problem framing (life-science lens)

A field rep's real bottleneck isn't the CRM's data model — it's the 90 seconds between
leaving one HCP's office and walking into the next one. Two behaviors follow from that:

1. **Whatever is fastest wins.** If typing into a 15-field form is slower than talking,
   the rep will do it in the car afterward from memory, or not at all — and call-note
   quality (and MLR compliance) suffers. The chat mode exists to close that gap, not as
   a novelty.
2. **The data still has to be audit-grade.** Pharma interaction logs feed sample
   accountability (PDMA), MLR review, and HCP engagement analytics. So both entry paths —
   form and chat — must resolve to the *exact same* structured schema and the *same*
   compliance screening. The chat is a faster typist, not a shortcut around governance.

That's the design thesis: **one canonical `Interaction` schema, two capture surfaces,
shared backend validation.**

## 2. High-level architecture

```
┌────────────────────────────┐        ┌───────────────────────────────────────────┐
│  React + Redux (frontend)  │        │                  FastAPI                    │
│                             │        │                                              │
│  LogInteractionScreen       │  REST  │  POST /api/interactions  ─────────────┐      │
│   ├─ StructuredForm  ───────┼───────▶│  PATCH /api/interactions/{id}         │      │
│   ├─ ChatInterface   ───────┼───────▶│  POST /api/interactions/chat    ──┐   │      │
│   └─ ExtractionTray         │        │        │                         │   ▼      ▼
└────────────────────────────┘        │        ▼                         │  interaction_service
                                       │  LangGraph agent (per session)   │   .create_interaction()
                                       │   extract_tray_node (tray only)  │   .update_interaction()
                                       │        │                        │      │
                                       │        ▼                        │      ▼
                                       │   agent_node ───▶ tools_node ────┘  Postgres (SQLAlchemy ORM)
                                       │      ▲               │  log_interaction
                                       │      └───────────────┤  edit_interaction
                                       │        (loop until    │  check_compliance
                                       │         no more        │  get_hcp_history
                                       │         tool calls)     │  schedule_follow_up
                                       │        │                              │
                                       │        ▼                              │
                                       │   Groq API (gemma2-9b-it /            │
                                       │             llama-3.3-70b-versatile)  │
                                       └───────────────────────────────────────┘
```

Both entry points call into the same `interaction_service` functions
(`create_interaction` / `update_interaction`) — the form posts an already-structured
payload directly; the chat agent's `log_interaction` / `edit_interaction` tools post
the same shape once the model has filled it in from conversation. This is what stops
the "AI path" from becoming a second, looser data model over time.

## 3. Frontend (React + Redux)

- `LogInteractionScreen` owns the mode toggle (`FORM` / `CHAT`) and renders one of the
  two capture surfaces plus, in chat mode, a live **Extraction Tray**.
- The Extraction Tray is the one deliberate "signature" element of this screen: as the
  rep talks, it lights up each CRM field the model has filled in, in the same order a
  paper call-report would ask for them, with anything still required flagged amber.
  The point is trust — the rep can see, turn by turn, that free text is becoming
  structured, auditable data before they ever hit confirm, and anything routed to MLR
  review is surfaced inline rather than silently held back.
- Redux (`interactionSlice`) holds: the structured form draft, the chat transcript +
  extracted fields + missing fields + compliance flags, and a shared `submission` status
  used by both surfaces so the success/error banner behaves identically either way.
- `interactionApi.js` is the only place that knows about HTTP — components dispatch
  thunks, never fetch directly.

## 4. Backend (FastAPI)

- `routers/interactions.py` — `POST /api/interactions` for the structured form.
- `routers/chat.py` — `POST /api/interactions/chat`, one call per chat turn. The route
  is deliberately thin: it loads/saves LangGraph checkpoint state and, only when the
  graph reaches `SAVED`, calls the same `interaction_service.create_interaction()` the
  form uses.
- `services/interaction_service.py` — the single write path: resolves or stubs the HCP
  record, upserts products, and persists samples/materials/follow-ups. This is where
  "one canonical schema" is actually enforced in code.

## 5. LangGraph agent design

### 5.1 Role of the agent

The LangGraph agent *is* the conversational half of the Log Interaction screen: it's
what turns "Visited Dr. Rao this morning about Cardiozol, dropped 2 samples" into a
structured, audit-grade row in `interactions` (plus its `interaction_products` /
`sample_drops` children), without the rep ever touching a form. Concretely it:

- carries the conversation (via LangGraph's `MemorySaver` checkpointer, keyed by
  `session_id`) so the rep can answer follow-up questions across turns without
  re-stating what they've already said;
- decides, turn by turn, whether it has enough information to act, needs to ask a
  clarifying question, or should call one of its five tools;
- is the only place compliance screening and persistence happen for the chat
  surface — every tool call that writes data routes through the same
  `interaction_service` functions the structured-form REST endpoints use, so chat
  and form entries are indistinguishable once saved (see §4).

Graph shape (`backend/app/agent/graph.py`):

```
extract_tray_node --> agent_node <--> tools_node
                            |
                            v (no more tool calls)
                           END
```

`extract_tray_node` is a cosmetic, once-per-turn `gemma2-9b-it` pass that keeps the
frontend's "Extraction Tray" panel populated live — it doesn't gate anything.
`agent_node` is `llama-3.3-70b-versatile` bound to the five tools below via
`bind_tools`; whenever it emits tool calls, `tools_node` executes them against the
DB and control returns to `agent_node` so it can react to the results (e.g. tell
the rep an entry was flagged for MLR review) before replying. A turn ends the
moment the model responds without calling a tool. `MAX_TOOL_HOPS` caps the
agent↔tools loop within a single turn to guard against runaway tool calling.

### 5.2 The five tools (`backend/app/agent/tools.py`)

| # | Tool | Sales-related activity it covers |
|---|---|---|
| 1 | **`log_interaction`** | Save a new HCP interaction. |
| 2 | **`edit_interaction`** | Correct/amend an interaction already logged. |
| 3 | `check_compliance` | MLR/off-label screen a piece of text. |
| 4 | `get_hcp_history` | Recall recent past interactions with a named HCP before/during a call. |
| 5 | `schedule_follow_up` | Capture a commitment made to an HCP (e.g. "send updated data next week"). |

**1. Log Interaction.** The LLM itself performs the entity extraction: its tool
schema (`LogInteractionArgs`) enumerates every field the CRM needs — HCP name,
interaction type, date/time, products discussed, sentiment, samples, etc. — and
`bind_tools`' function-calling forces the model to populate them from the free-text
conversation before the call is valid. Inside the tool body two more LLM steps run:
`_tighten_notes` (a fast `gemma2-9b-it` pass) condenses a rambling dictated note
into 1-2 clean sentences if it's long, and `_screen_compliance`
(`llama-3.3-70b-versatile`) screens those notes for off-label/inducement language
*before* the row is written — an interaction with flags is saved as
`PENDING_REVIEW` rather than `SUBMITTED`, never silently dropped or silently
approved. The actual write goes through `interaction_service.create_interaction`,
the same function the structured-form endpoint calls.

**2. Edit Interaction.** Takes an `interaction_id` (optional — defaults to the most
recently logged interaction for the rep if omitted, so "actually, change the
interest level to 5" works without the rep knowing any IDs) and a `updates` dict of
field → new value, restricted server-side to `EDITABLE_INTERACTION_FIELDS`
(identity/provenance fields like `hcp_id` and `source_transcript` aren't editable —
they're the record's history, not its data). If the edit touches
`key_message_notes`, compliance is re-screened, so an edit can't quietly move a
flagged interaction back to `SUBMITTED` or vice versa. Writes through
`interaction_service.update_interaction`, which also backs the REST
`PATCH /api/interactions/{id}` endpoint used by the structured-form path — one
edit code path for both surfaces, same as logging.

**3. Check Compliance.** Screens arbitrary text against
`COMPLIANCE_TRIGGER_HINT` (off-label use, unapproved indications, unsubstantiated
superiority claims, pricing/inducement language) via `llama-3.3-70b-versatile` in
JSON mode, returning short flag codes plus a rationale. `log_interaction` and
`edit_interaction` call this internally, but the agent can also invoke it directly
when a rep asks "is it okay to say X".

**4. Get HCP History.** Read-only lookup of a named HCP's most recent interactions
(date, type, notes, sentiment, products) — lets the agent (and the rep) recall
context ("what did we discuss with Dr. Rao last time?") instead of re-asking for
information already on file, and gives it grounding to sanity-check a new log
against past visits.

**5. Schedule Follow-up.** Creates a row in the new `follow_ups` table — a
commitment tied to an HCP, optionally linked to the interaction it was raised
during, distinct from an interaction itself (a rep can promise a follow-up without
that promise being a loggable "visit").

Each tool opens its own short-lived DB session (`SessionLocal()`) rather than
sharing FastAPI's request-scoped session, since tool execution happens inside a
LangGraph node, not a request handler — this also means the tools are usable
outside the chat endpoint (e.g. from a scheduled job) with no changes.

State is checkpointed per `session_id` (`MemorySaver`, keyed by `thread_id`), so a
rep can back out of the chat mid-conversation and resume later without
re-explaining themselves. Swap `MemorySaver` for a Postgres/Redis checkpointer for
multi-instance deployments.

## 6. Model routing (Groq)

| Step | Model | Why |
|---|---|---|
| Extraction Tray field extraction (`extract_tray_node`, every turn); note-tightening inside `log_interaction` | `gemma2-9b-it` | Runs once per message, needs to be fast and cheap; bounded, schema-shaped tasks with a JSON-mode response, which small instruction-tuned models handle well. |
| Tool-calling agent loop (`agent_node`); `check_compliance` reasoning | `llama-3.3-70b-versatile` | Deciding which of the five tools to call (if any) needs stronger instruction-following and function-calling reliability than a small model gives on Groq; off-label detection needs more nuance than slot-filling; runs once per turn, not per field, so the extra latency is worth it. |

`gemma2-9b-it` is called through the raw `groq` Python SDK (`app/agent/groq_client.py`).
`llama-3.3-70b-versatile` is additionally wrapped in `langchain_groq.ChatGroq` so it can be
bound to the five LangChain tools via `.bind_tools()` for the agent loop. Both hit
`console.groq.com`'s OpenAI-compatible `/chat/completions` endpoint; see
`backend/.env.example` for the token setup.

## 7. Data model highlights (life-science specific)

- `Interaction.entry_mode` (`STRUCTURED_FORM` / `CONVERSATIONAL`) — kept for analytics on
  which capture path reps actually use, and because chat-originated rows also retain
  `source_transcript` for audit.
- `Interaction.compliance_flags` + `status = PENDING_REVIEW` — any interaction (from
  either surface) that trips the compliance screen is routed to MLR review before it
  counts as `SUBMITTED`, rather than being silently blocked or silently allowed.
- `SampleDrop.hcp_signature_captured` — samples are a PDMA-regulated event; the schema
  carries the signature-capture flag as a first-class field rather than burying it in
  free text.
- `ai_confidence_score` on `Interaction` — reserved for surfacing "the model wasn't sure
  about this one" in a review queue, distinct from the compliance flag (confidence is
  about extraction accuracy, compliance is about content).

## 8. What's out of scope here (by design)

This deliverable is the Log Interaction screen only: auth/IAM (`rep_id` is passed in as
a header/param, assumed to come from an existing session), the broader CRM shell (HCP
360 view, territory management, sample inventory), and CI/deployment config. The DB
schema and service layer are written so those modules can be built against the same
`hcps` / `products` / `interactions` tables without rework.
