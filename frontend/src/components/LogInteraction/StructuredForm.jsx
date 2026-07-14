import React from "react";
import { useDispatch, useSelector } from "react-redux";
import {
  updateFormField,
  updateProductRow,
  addProductRow,
  removeProductRow,
  submitForm,
} from "../../redux/interactionSlice";

const REP_ID = "demo-rep-001";

const INTERACTION_TYPES = [
  ["IN_PERSON_VISIT", "In-person visit"],
  ["VIRTUAL_MEETING", "Virtual meeting"],
  ["PHONE_CALL", "Phone call"],
  ["EMAIL", "Email"],
  ["CONFERENCE_BOOTH", "Conference booth"],
  ["SPEAKER_PROGRAM", "Speaker program"],
];

export default function StructuredForm() {
  const dispatch = useDispatch();
  const form = useSelector((s) => s.interaction.form);
  const status = useSelector((s) => s.interaction.submission.status);

  const field = (name) => ({
    value: form[name],
    onChange: (e) => {
      const value = e.target.type === "checkbox" ? e.target.checked : e.target.value;
      dispatch(updateFormField({ field: name, value }));
    },
  });

  const handleSubmit = (e) => {
    e.preventDefault();
    dispatch(
      submitForm({
        repId: REP_ID,
        payload: {
          ...form,
          duration_minutes: form.duration_minutes ? Number(form.duration_minutes) : null,
          interest_level: Number(form.interest_level),
          products_discussed: form.products_discussed.filter((p) => p.product_name.trim()),
        },
      })
    );
  };

  return (
    <form className="form" onSubmit={handleSubmit}>
      <div className="form__grid">
        <label className="field">
          <span className="field__label">HCP name</span>
          <input className="field__input" placeholder="Dr. Ananya Rao" required {...field("hcp_name")} />
        </label>

        <label className="field">
          <span className="field__label">Interaction type</span>
          <select className="field__input" {...field("interaction_type")}>
            {INTERACTION_TYPES.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>

        <label className="field">
          <span className="field__label">Date &amp; time</span>
          <input className="field__input" type="datetime-local" required {...field("interaction_datetime")} />
        </label>

        <label className="field">
          <span className="field__label">Duration (min)</span>
          <input className="field__input" type="number" min="0" {...field("duration_minutes")} />
        </label>

        <label className="field field--wide">
          <span className="field__label">Location / channel</span>
          <input className="field__input" placeholder="Sunrise Clinic, Andheri" {...field("channel_location")} />
        </label>
      </div>

      <fieldset className="form__section">
        <legend>Products discussed</legend>
        {form.products_discussed.map((row, i) => (
          <div className="product-row" key={i}>
            <input
              className="field__input"
              placeholder="Product name"
              value={row.product_name}
              onChange={(e) => dispatch(updateProductRow({ index: i, field: "product_name", value: e.target.value }))}
            />
            <input
              className="field__input"
              placeholder="HCP reaction / notes"
              value={row.reaction_notes}
              onChange={(e) => dispatch(updateProductRow({ index: i, field: "reaction_notes", value: e.target.value }))}
            />
            <button type="button" className="icon-btn" onClick={() => dispatch(removeProductRow(i))} aria-label="Remove product">
              ×
            </button>
          </div>
        ))}
        <button type="button" className="btn btn--ghost" onClick={() => dispatch(addProductRow())}>
          + Add product
        </button>
      </fieldset>

      <label className="field">
        <span className="field__label">Discussion notes</span>
        <textarea className="field__input field__input--textarea" rows={4} {...field("key_message_notes")} />
      </label>

      <div className="form__grid">
        <label className="field">
          <span className="field__label">HCP sentiment</span>
          <select className="field__input" {...field("hcp_sentiment")}>
            <option value="POSITIVE">Positive</option>
            <option value="NEUTRAL">Neutral</option>
            <option value="NEGATIVE">Negative</option>
          </select>
        </label>

        <label className="field">
          <span className="field__label">Interest level (1–5)</span>
          <input className="field__input" type="range" min="1" max="5" {...field("interest_level")} />
        </label>

        <label className="field field--checkbox">
          <input type="checkbox" checked={form.follow_up_required} onChange={field("follow_up_required").onChange} />
          <span>Follow-up required</span>
        </label>

        {form.follow_up_required && (
          <label className="field field--wide">
            <span className="field__label">Follow-up action</span>
            <input className="field__input" {...field("follow_up_action")} />
          </label>
        )}
      </div>

      <div className="form__actions">
        <button type="submit" className="btn btn--primary" disabled={status === "loading"}>
          {status === "loading" ? "Saving…" : "Save interaction"}
        </button>
      </div>
    </form>
  );
}
