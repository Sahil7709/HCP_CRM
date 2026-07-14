import { createSlice, createAsyncThunk, nanoid } from "@reduxjs/toolkit";
import { submitStructuredInteraction, sendChatTurn } from "../api/interactionApi";

const emptyForm = {
  hcp_name: "",
  interaction_type: "IN_PERSON_VISIT",
  interaction_datetime: "",
  duration_minutes: "",
  channel_location: "",
  key_message_notes: "",
  hcp_sentiment: "NEUTRAL",
  interest_level: 3,
  follow_up_required: false,
  follow_up_action: "",
  products_discussed: [{ product_name: "", reaction_notes: "" }],
  samples_dropped: [],
  materials_shared: [],
};

export const submitForm = createAsyncThunk(
  "interaction/submitForm",
  async ({ payload, repId }) => submitStructuredInteraction(payload, repId)
);

export const sendMessage = createAsyncThunk(
  "interaction/sendMessage",
  async ({ sessionId, message, repId }) => sendChatTurn(sessionId, message, repId)
);

const initialState = {
  mode: "FORM", // "FORM" | "CHAT"
  form: emptyForm,
  chat: {
    sessionId: nanoid(),
    messages: [], // {role: 'user'|'assistant', content}
    extractedFields: {},
    missingFields: [],
    complianceFlags: [],
    stage: "CHATTING",
    isSending: false,
  },
  submission: {
    status: "idle", // idle | loading | succeeded | failed
    error: null,
    savedInteractionId: null,
  },
};

const interactionSlice = createSlice({
  name: "interaction",
  initialState,
  reducers: {
    setMode(state, action) {
      state.mode = action.payload;
    },
    updateFormField(state, action) {
      const { field, value } = action.payload;
      state.form[field] = value;
    },
    updateProductRow(state, action) {
      const { index, field, value } = action.payload;
      state.form.products_discussed[index][field] = value;
    },
    addProductRow(state) {
      state.form.products_discussed.push({ product_name: "", reaction_notes: "" });
    },
    removeProductRow(state, action) {
      state.form.products_discussed.splice(action.payload, 1);
    },
    resetForm(state) {
      state.form = emptyForm;
      state.submission = initialState.submission;
    },
    resetChat(state) {
      state.chat = { ...initialState.chat, sessionId: nanoid() };
      state.submission = initialState.submission;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(submitForm.pending, (state) => {
        state.submission.status = "loading";
        state.submission.error = null;
      })
      .addCase(submitForm.fulfilled, (state, action) => {
        state.submission.status = "succeeded";
        state.submission.savedInteractionId = action.payload.id;
      })
      .addCase(submitForm.rejected, (state, action) => {
        state.submission.status = "failed";
        state.submission.error = action.error.message;
      })
      .addCase(sendMessage.pending, (state, action) => {
        state.chat.isSending = true;
        state.chat.messages.push({ role: "user", content: action.meta.arg.message });
      })
      .addCase(sendMessage.fulfilled, (state, action) => {
        const data = action.payload;
        state.chat.isSending = false;
        state.chat.messages.push({ role: "assistant", content: data.reply });
        state.chat.extractedFields = data.extracted_fields;
        state.chat.missingFields = data.missing_fields;
        state.chat.complianceFlags = data.compliance_flags;
        state.chat.stage = data.stage;
        if (data.stage === "SAVED" || data.stage === "EDITED") {
          state.submission.status = "succeeded";
          state.submission.savedInteractionId = data.interaction_id;
        }
      })
      .addCase(sendMessage.rejected, (state, action) => {
        state.chat.isSending = false;
        state.chat.messages.push({
          role: "assistant",
          content: "Sorry, something went wrong reaching the assistant. Please try again.",
        });
        state.submission.error = action.error.message;
      });
  },
});

export const {
  setMode,
  updateFormField,
  updateProductRow,
  addProductRow,
  removeProductRow,
  resetForm,
  resetChat,
} = interactionSlice.actions;

export default interactionSlice.reducer;
