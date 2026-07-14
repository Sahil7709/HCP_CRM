import React from "react";
import { useDispatch, useSelector } from "react-redux";
import { setMode } from "../../redux/interactionSlice";
import StructuredForm from "./StructuredForm";
import ChatInterface from "./ChatInterface";
import ExtractionTray from "./ExtractionTray";
import "./LogInteraction.css";

export default function LogInteractionScreen() {
  const dispatch = useDispatch();
  const mode = useSelector((s) => s.interaction.mode);
  const submission = useSelector((s) => s.interaction.submission);
  const chat = useSelector((s) => s.interaction.chat);

  return (
    <div className="log-screen">
      <header className="log-screen__header">
        <div>
          <p className="log-screen__eyebrow">HCP Module</p>
          <h1 className="log-screen__title">Log Interaction</h1>
        </div>

        <div className="mode-toggle" role="tablist" aria-label="Interaction entry mode">
          <button
            role="tab"
            aria-selected={mode === "FORM"}
            className={`mode-toggle__option ${mode === "FORM" ? "is-active" : ""}`}
            onClick={() => dispatch(setMode("FORM"))}
          >
            Structured form
          </button>
          <button
            role="tab"
            aria-selected={mode === "CHAT"}
            className={`mode-toggle__option ${mode === "CHAT" ? "is-active" : ""}`}
            onClick={() => dispatch(setMode("CHAT"))}
          >
            Tell the assistant
          </button>
          <span className={`mode-toggle__indicator mode-toggle__indicator--${mode.toLowerCase()}`} />
        </div>
      </header>

      {submission.status === "succeeded" && (
        <div className="log-screen__banner log-screen__banner--success">
          {chat.stage === "EDITED" ? "Interaction updated" : "Interaction saved"}
          {submission.savedInteractionId ? ` · #${submission.savedInteractionId.slice(0, 8)}` : ""}.
        </div>
      )}
      {submission.status === "failed" && (
        <div className="log-screen__banner log-screen__banner--error">
          {submission.error || "Something went wrong saving this interaction."}
        </div>
      )}

      <div className={`log-screen__body ${mode === "CHAT" ? "log-screen__body--split" : ""}`}>
        <div className="log-screen__main">
          {mode === "FORM" ? <StructuredForm /> : <ChatInterface />}
        </div>
        {mode === "CHAT" && (
          <aside className="log-screen__side">
            <ExtractionTray />
          </aside>
        )}
      </div>
    </div>
  );
}
