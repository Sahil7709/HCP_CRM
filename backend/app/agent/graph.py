"""
LangGraph agent for the "Log Interaction via chat" mode.

Flow
----
extract_tray_node -> agent_node -> (tools_node -> agent_node)* -> END

`extract_tray_node` is a cosmetic, once-per-turn gemma2-9b-it pass that keeps the
frontend's live "Extraction Tray" panel populated; it doesn't gate anything.

`agent_node` is the actual brain: llama-3.3-70b-versatile bound to the five tools
in app.agent.tools (see prompts.AGENT_SYSTEM_PROMPT for the tool descriptions the
model sees). If it emits tool calls, `tools_node` executes them against the DB and
the loop returns to `agent_node` so it can react to the results; once it replies
without calling a tool, the turn ends.

State is checkpointed per session_id via LangGraph's MemorySaver, so a rep can
leave the screen and come back mid-conversation without losing progress.
"""
import json
from datetime import datetime, timezone

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from app.agent.state import AgentState, REQUIRED_FIELDS
from app.agent.prompts import EXTRACTION_SYSTEM_PROMPT, AGENT_SYSTEM_PROMPT
from app.agent import groq_client
from app.agent.tools import build_tools

MAX_TOOL_HOPS = 4


def extract_tray_node(state: AgentState) -> AgentState:
    last_message = state["messages"][-1]
    user_prompt = json.dumps({
        "known_fields": state.get("extracted", {}),
        "reference_date": datetime.now(timezone.utc).isoformat(),
        "new_message": last_message.content,
    })
    delta = groq_client.extract_fields(EXTRACTION_SYSTEM_PROMPT, user_prompt)

    merged = {**state.get("extracted", {}), **{k: v for k, v in delta.items() if v not in (None, "", [])}}
    missing = [f for f in REQUIRED_FIELDS if not merged.get(f)]

    return {
        "extracted": merged,
        "missing_fields": missing,
        "tool_hops": 0,
        "last_action": "NONE",
    }


def agent_node(state: AgentState) -> AgentState:
    llm = groq_client.get_tool_calling_llm()
    tools = build_tools(state["rep_id"])
    llm_with_tools = llm.bind_tools(tools)

    system = SystemMessage(content=AGENT_SYSTEM_PROMPT.format(
        reference_date=datetime.now(timezone.utc).isoformat(),
        last_saved_interaction_id=state.get("last_saved_interaction_id") or "none yet",
    ))
    response = llm_with_tools.invoke([system, *state["messages"]])
    return {"messages": [response]}


def _route_after_agent(state: AgentState) -> str:
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.tool_calls and state.get("tool_hops", 0) < MAX_TOOL_HOPS:
        return "tools_node"
    return END


def tools_node(state: AgentState) -> AgentState:
    last_ai = state["messages"][-1]
    tools_by_name = {t.name: t for t in build_tools(state["rep_id"])}

    tool_messages = []
    updates = {"last_action": state.get("last_action", "NONE")}

    for call in last_ai.tool_calls:
        tool = tools_by_name.get(call["name"])
        result = tool.invoke(call["args"]) if tool else {"status": "error", "error": f"Unknown tool {call['name']}"}
        tool_messages.append(ToolMessage(content=json.dumps(result, default=str), tool_call_id=call["id"]))

        name, status = call["name"], result.get("status")
        if name == "log_interaction" and status == "saved":
            updates["last_saved_interaction_id"] = result["interaction_id"]
            updates["compliance_flags"] = result.get("compliance_flags", [])
            updates["last_action"] = "LOGGED"
        elif name == "edit_interaction" and status == "updated":
            updates["last_saved_interaction_id"] = result["interaction_id"]
            updates["compliance_flags"] = result.get("compliance_flags", [])
            updates["last_action"] = "EDITED"
        elif name == "check_compliance":
            updates["compliance_flags"] = result.get("flags", [])
            updates["last_action"] = "COMPLIANCE_CHECKED"
        elif name == "get_hcp_history":
            updates["last_action"] = "HISTORY_LOOKED_UP"
        elif name == "schedule_follow_up" and status == "scheduled":
            updates["last_action"] = "FOLLOW_UP_SCHEDULED"

    updates["messages"] = tool_messages
    updates["tool_hops"] = state.get("tool_hops", 0) + 1
    return updates


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("extract_tray_node", extract_tray_node)
    graph.add_node("agent_node", agent_node)
    graph.add_node("tools_node", tools_node)

    graph.set_entry_point("extract_tray_node")
    graph.add_edge("extract_tray_node", "agent_node")
    graph.add_conditional_edges("agent_node", _route_after_agent, {"tools_node": "tools_node", END: END})
    graph.add_edge("tools_node", "agent_node")

    return graph.compile(checkpointer=MemorySaver())


# Singleton compiled graph, reused across requests. MemorySaver keeps
# per-session_id state via the `thread_id` field in the config.
interaction_agent = build_graph()
