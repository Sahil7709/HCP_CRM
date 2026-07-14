const BASE_URL = "/api/interactions";

export async function submitStructuredInteraction(payload, repId) {
  const res = await fetch(BASE_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Rep-Id": repId,
    },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to save interaction");
  }
  return res.json();
}

export async function sendChatTurn(sessionId, message, repId) {
  const res = await fetch(`${BASE_URL}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, message, rep_id: repId }),
  });
  if (!res.ok) {
    throw new Error("Chat request failed");
  }
  return res.json();
}
