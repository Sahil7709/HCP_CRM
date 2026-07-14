"""
Thin wrapper around the Groq API (https://console.groq.com/docs/models).

Model routing strategy
-----------------------
gemma2-9b-it        -> fast, cheap, used for the high-frequency, low-ambiguity
                        job of pulling structured fields out of a rep's raw
                        sentence on every turn of the chat.
llama-3.3-70b-versatile -> reserved for the lower-frequency, higher-stakes
                        steps: compliance/off-label screening and writing the
                        natural-language clarifying question / confirmation
                        summary that the rep actually reads. These need better
                        instruction-following and nuance than field extraction
                        does, and they run once per turn (not once per field),
                        so the extra latency/cost is worth it.
"""
import json
import logging
from typing import Any, Dict

from groq import Groq
from langchain_groq import ChatGroq

from app.config import settings

logger = logging.getLogger(__name__)

_client: Groq | None = None
_tool_llm: ChatGroq | None = None


def get_client() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=settings.groq_api_key)
    return _client


def _chat(model: str, system_prompt: str, user_prompt: str, json_mode: bool = False, temperature: float = 0.2) -> str:
    client = get_client()
    kwargs: Dict[str, Any] = {
        "model": model,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    completion = client.chat.completions.create(**kwargs)
    return completion.choices[0].message.content


def extract_fields(system_prompt: str, user_prompt: str) -> Dict[str, Any]:
    """Field extraction — routed to gemma2-9b-it."""
    raw = _chat(settings.groq_extraction_model, system_prompt, user_prompt, json_mode=True, temperature=0.0)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Extraction model returned non-JSON output, falling back to empty dict: %s", raw)
        return {}


def reason(system_prompt: str, user_prompt: str, json_mode: bool = False) -> str:
    """Compliance review / clarifying question / confirmation copy — routed to llama-3.3-70b-versatile."""
    return _chat(settings.groq_reasoning_model, system_prompt, user_prompt, json_mode=json_mode, temperature=0.3)


def get_tool_calling_llm() -> ChatGroq:
    """The LangGraph agent's "brain": llama-3.3-70b-versatile bound with the five
    sales-activity tools (see app.agent.tools). Field-level extraction stays on the
    raw Groq client above with gemma2-9b-it — tool-calling reliability on Groq is
    strongest on the larger instruction-tuned model, and this is a once-per-turn
    call, not a per-field one, so the extra latency is acceptable.
    """
    global _tool_llm
    if _tool_llm is None:
        _tool_llm = ChatGroq(model=settings.groq_reasoning_model, api_key=settings.groq_api_key, temperature=0.2)
    return _tool_llm
