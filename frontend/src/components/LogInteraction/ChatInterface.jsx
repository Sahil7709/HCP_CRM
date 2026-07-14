import React, { useState, useRef, useEffect } from "react";
import { useDispatch, useSelector } from "react-redux";
import { sendMessage, resetChat } from "../../redux/interactionSlice";

const REP_ID = "demo-rep-001"; // replace with authenticated user id from the IAM/session module

const STARTER_PROMPTS = [
  "Visited Dr. Rao this morning about Cardiozol",
  "30 min call with Dr. Iyer, dropped 2 samples of Nefrolex",
];

export default function ChatInterface() {
  const dispatch = useDispatch();
  const { sessionId, messages, isSending, stage } = useSelector((s) => s.interaction.chat);
  const [draft, setDraft] = useState("");
  const scrollRef = useRef(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, isSending]);

  const send = (text) => {
    const message = text ?? draft;
    if (!message.trim() || isSending) return;
    dispatch(sendMessage({ sessionId, message, repId: REP_ID }));
    setDraft("");
  };

  return (
    <div className="chat">
      <div className="chat__transcript" ref={scrollRef}>
        {messages.length === 0 && (
          <div className="chat__empty">
            <p>Describe the interaction in your own words — I'll fill in the record as we go.</p>
            <div className="chat__starters">
              {STARTER_PROMPTS.map((p) => (
                <button key={p} className="chat__starter" onClick={() => send(p)}>
                  {p}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`chat__bubble chat__bubble--${m.role}`}>
            {m.content}
          </div>
        ))}
        {isSending && <div className="chat__bubble chat__bubble--assistant chat__bubble--typing">Thinking…</div>}
      </div>

      {(stage === "SAVED" || stage === "EDITED") && (
        <div className="chat__saved-actions">
          <p className="chat__saved-hint">
            {stage === "SAVED" ? "Saved. " : "Updated. "}
            Keep going to change something (the assistant can edit it), or start fresh.
          </p>
          <button className="btn btn--secondary" onClick={() => dispatch(resetChat())}>
            Log another interaction
          </button>
        </div>
      )}
      <form
        className="chat__composer"
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
      >
        <input
          className="chat__input"
          placeholder={
            stage === "SAVED" || stage === "EDITED"
              ? 'e.g. "Actually, change the interest level to 5"'
              : "Type a message…"
          }
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
        />
        <button type="submit" className="btn btn--primary" disabled={isSending || !draft.trim()}>
          Send
        </button>
      </form>
    </div>
  );
}
