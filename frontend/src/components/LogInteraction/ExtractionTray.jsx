import React from "react";
import { useSelector } from "react-redux";

const FIELD_LABELS = {
  hcp_name: "HCP",
  interaction_type: "Interaction type",
  interaction_datetime: "Date & time",
  channel_location: "Location",
  products_discussed: "Products discussed",
  key_message_notes: "Notes",
  hcp_sentiment: "Sentiment",
  interest_level: "Interest level",
};

function formatValue(key, value) {
  if (value == null || value === "") return null;
  if (key === "products_discussed" && Array.isArray(value)) {
    return value.map((p) => p.product_name).filter(Boolean).join(", ") || null;
  }
  if (Array.isArray(value)) return value.join(", ");
  return String(value);
}

export default function ExtractionTray() {
  const { extractedFields, missingFields, complianceFlags } = useSelector((s) => s.interaction.chat);
  const trackedKeys = Object.keys(FIELD_LABELS);

  return (
    <div className="extraction-tray">
      <p className="extraction-tray__heading">Captured so far</p>
      <ul className="extraction-tray__list">
        {trackedKeys.map((key) => {
          const value = formatValue(key, extractedFields[key]);
          const isMissing = missingFields.includes(key);
          return (
            <li key={key} className={`extraction-tray__item ${value ? "is-filled" : ""}`}>
              <span className={`extraction-tray__dot ${value ? "is-filled" : isMissing ? "is-required" : ""}`} />
              <div>
                <p className="extraction-tray__label">{FIELD_LABELS[key]}</p>
                <p className="extraction-tray__value">{value || (isMissing ? "Still needed" : "Optional")}</p>
              </div>
            </li>
          );
        })}
      </ul>

      {complianceFlags.length > 0 && (
        <div className="extraction-tray__compliance">
          <p className="extraction-tray__compliance-title">Flagged for MLR review</p>
          <ul>
            {complianceFlags.map((flag) => (
              <li key={flag}>{flag.replaceAll("_", " ").toLowerCase()}</li>
            ))}
          </ul>
        </div>
      )}

      <p className="extraction-tray__footnote">
        Every field you see here will be written to the HCP's record exactly as shown — say
        "change…" any time to correct something before you confirm.
      </p>
    </div>
  );
}
