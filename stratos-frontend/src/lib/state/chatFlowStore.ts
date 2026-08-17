import type { ReportView } from "@/lib/api/orchestratorClient";
import type { AppStage, StreamEnvelope } from "@/lib/sse/events";

export type Role = "user" | "assistant" | "system";

export type ChatMessage = {
  id: string;
  role: Role;
  content: string;
  meta?: string;
};

export type ProgressEvent = {
  id: string;
  label: string;
  status: "running" | "done" | "error";
  timestamp: string;
};

export type SectionItem = {
  sectionId: string;
  title: string;
  status: "pending" | "streaming" | "done";
  partialText: string;
};

export type ChatFlowState = {
  stage: AppStage;
  sessionId: string | null;
  reportId: string | null;
  summaryForConsent: string | null;
  messages: ChatMessage[];
  progressEvents: ProgressEvent[];
  sectionsById: Record<string, SectionItem>;
  sectionOrder: string[];
  finalReport: ReportView | null;
  error: string | null;
  connectionStatus: "idle" | "connected" | "disconnected";
  loginToken: string | null;
};

export type ChatFlowAction =
  | { type: "SET_LOGIN_TOKEN"; token: string | null }
  | { type: "SET_SESSION"; sessionId: string }
  | { type: "SET_REPORT"; reportId: string }
  | { type: "ADD_MESSAGE"; message: ChatMessage }
  | { type: "SET_STAGE"; stage: AppStage }
  | { type: "SET_CONNECTION_STATUS"; status: ChatFlowState["connectionStatus"] }
  | { type: "ADD_PROGRESS"; event: ProgressEvent }
  | { type: "SET_SUMMARY"; summary: string | null }
  | { type: "UPSERT_SECTION"; section: SectionItem }
  | { type: "APPEND_SECTION_CHUNK"; sectionId: string; title?: string; text: string }
  | { type: "SET_SECTION_STATUS"; sectionId: string; status: SectionItem["status"] }
  | { type: "SET_FINAL_REPORT"; report: ReportView }
  | { type: "SET_ERROR"; error: string | null }
  | { type: "RESET" };

export const initialState: ChatFlowState = {
  stage: "clarifying",
  sessionId: null,
  reportId: null,
  summaryForConsent: null,
  messages: [],
  progressEvents: [],
  sectionsById: {},
  sectionOrder: [],
  finalReport: null,
  error: null,
  connectionStatus: "idle",
  loginToken: null,
};

export function chatFlowReducer(
  state: ChatFlowState,
  action: ChatFlowAction,
): ChatFlowState {
  switch (action.type) {
    case "SET_LOGIN_TOKEN":
      return { ...state, loginToken: action.token };
    case "SET_SESSION":
      return { ...state, sessionId: action.sessionId };
    case "SET_REPORT":
      return { ...state, reportId: action.reportId };
    case "ADD_MESSAGE":
      return { ...state, messages: [...state.messages, action.message] };
    case "SET_STAGE":
      return { ...state, stage: action.stage };
    case "SET_CONNECTION_STATUS":
      return { ...state, connectionStatus: action.status };
    case "ADD_PROGRESS":
      if (state.progressEvents.some((event) => event.id === action.event.id)) {
        return state;
      }
      return { ...state, progressEvents: [...state.progressEvents, action.event] };
    case "SET_SUMMARY":
      return { ...state, summaryForConsent: action.summary };
    case "UPSERT_SECTION": {
      const isNew = !state.sectionsById[action.section.sectionId];
      return {
        ...state,
        sectionsById: {
          ...state.sectionsById,
          [action.section.sectionId]: action.section,
        },
        sectionOrder: isNew
          ? [...state.sectionOrder, action.section.sectionId]
          : state.sectionOrder,
      };
    }
    case "APPEND_SECTION_CHUNK": {
      const existing = state.sectionsById[action.sectionId];
      const isNew = !existing;
      const section: SectionItem = existing
        ? {
            ...existing,
            title: action.title || existing.title,
            partialText: existing.partialText + action.text,
            status: "streaming",
          }
        : {
            sectionId: action.sectionId,
            title: action.title || "Untitled Section",
            partialText: action.text,
            status: "streaming",
          };
      return {
        ...state,
        sectionsById: { ...state.sectionsById, [action.sectionId]: section },
        sectionOrder: isNew
          ? [...state.sectionOrder, action.sectionId]
          : state.sectionOrder,
      };
    }
    case "SET_SECTION_STATUS": {
      const existing = state.sectionsById[action.sectionId];
      if (!existing) {
        return state;
      }
      return {
        ...state,
        sectionsById: {
          ...state.sectionsById,
          [action.sectionId]: { ...existing, status: action.status },
        },
      };
    }
    case "SET_FINAL_REPORT":
      return { ...state, finalReport: action.report };
    case "SET_ERROR":
      return { ...state, error: action.error };
    case "RESET":
      return { ...initialState, loginToken: state.loginToken };
    default:
      return state;
  }
}

function stringValue(input: unknown): string {
  return typeof input === "string" ? input : "";
}

function buildProgressLabel(eventType: string): string {
  const labels: Record<string, string> = {
    clarification_started: "Clarification started",
    clarification_completed: "Clarification complete",
    outline_accepted: "Outline accepted",
    outline_ready: "Outline generated",
    research_started: "Research pipeline started",
    searching_sources: "Searching high-signal sources",
    research_done: "Research completed",
    research_failed: "Research failed",
    scanning_trends: "Scanning trend signals",
    trend_ready: "Trend analysis completed",
    trend_failed: "Trend scan failed (continuing without trends)",
    section_writing_started: "Writing sections",
    sections_done: "All sections written",
    report_assembled: "Assembling report",
    export_done: "Export finished",
  };
  return labels[eventType] ?? `Event: ${eventType}`;
}

const RESEARCH_PROGRESS_EVENTS = new Set([
  "research_started",
  "searching_sources",
  "research_done",
  "research_failed",
  "outline_ready",
  "outline_accepted",
  "scanning_trends",
  "trend_ready",
  "trend_failed",
  "section_writing_started",
  "sections_done",
  "report_assembled",
]);

export function eventToActions(event: StreamEnvelope): ChatFlowAction[] {
  const now = new Date().toISOString();
  const payload = event.payload ?? {};
  const actions: ChatFlowAction[] = [];

  if (event.type === "clarification_update") {
    const summary = stringValue(payload.mirror_summary);
    const nextQuestion = stringValue(payload.next_question);
    const confidence = stringValue(payload.confidence_score);
    if (summary) {
      actions.push({
        type: "ADD_MESSAGE",
        message: {
          id: `assistant-summary-${now}`,
          role: "assistant",
          content: summary,
          meta: confidence ? `Confidence ${confidence}` : undefined,
        },
      });
    }
    if (nextQuestion) {
      actions.push({
        type: "ADD_MESSAGE",
        message: {
          id: `assistant-question-${now}`,
          role: "assistant",
          content: nextQuestion,
        },
      });
    }
  }

  if (event.type === "clarification_consent_requested") {
    actions.push({ type: "SET_STAGE", stage: "awaitingConsent" });
    actions.push({
      type: "SET_SUMMARY",
      summary: stringValue(payload.summary) || "Your idea is clear. Start research?",
    });
  }

  if (event.type === "outline_ready") {
    const reportId = stringValue(payload.report_id);
    if (reportId) {
      actions.push({ type: "SET_REPORT", reportId });
    }
    const sections = Array.isArray(payload.sections) ? payload.sections : [];
    for (const raw of sections) {
      const section = raw as Record<string, unknown>;
      const sectionId = stringValue(section.section_id);
      if (!sectionId) {
        continue;
      }
      actions.push({
        type: "UPSERT_SECTION",
        section: {
          sectionId,
          title: stringValue(section.title) || "Untitled Section",
          partialText: "",
          status: "pending",
        },
      });
    }
  }

  if (RESEARCH_PROGRESS_EVENTS.has(event.type)) {
    actions.push({ type: "SET_STAGE", stage: "researching" });
    actions.push({
      type: "ADD_PROGRESS",
      event: {
        id: `${event.type}-${now}`,
        label: buildProgressLabel(event.type),
        status: event.type.endsWith("_done")
          ? "done"
          : event.type.includes("failed")
            ? "error"
            : "running",
        timestamp: now,
      },
    });
  }

  if (event.type === "section_writing_started") {
    actions.push({ type: "SET_STAGE", stage: "streamingSections" });
  }

  if (event.type === "section_started") {
    const sectionId = stringValue(payload.section_id);
    if (sectionId) {
      actions.push({ type: "SET_STAGE", stage: "streamingSections" });
      actions.push({ type: "SET_SECTION_STATUS", sectionId, status: "streaming" });
    }
  }

  if (event.type === "section_chunk") {
    const sectionId = stringValue(payload.section_id);
    const text = stringValue(payload.text) || stringValue(payload.chunk_text);
    if (sectionId) {
      actions.push({ type: "SET_STAGE", stage: "streamingSections" });
      actions.push({
        type: "APPEND_SECTION_CHUNK",
        sectionId,
        title: stringValue(payload.title) || undefined,
        text,
      });
    }
  }

  if (event.type === "section_done") {
    const sectionId = stringValue(payload.section_id);
    if (sectionId) {
      actions.push({ type: "SET_SECTION_STATUS", sectionId, status: "done" });
    }
  }

  // export_done flips to reportReady; the real report is fetched by the view
  // layer (it needs an async call, which a pure reducer cannot do).
  if (event.type === "export_done") {
    const reportId = stringValue(payload.report_id);
    if (reportId) {
      actions.push({ type: "SET_REPORT", reportId });
    }
    actions.push({ type: "SET_STAGE", stage: "reportReady" });
  }

  if (event.type.includes("failed")) {
    // trend_failed is non-fatal: the pipeline continues without trend items.
    const errorMessage = stringValue(payload.error) || `${event.type}`;
    if (event.type !== "trend_failed") {
      actions.push({ type: "SET_ERROR", error: errorMessage });
      actions.push({ type: "SET_STAGE", stage: "failed" });
    }
  }

  return actions;
}
