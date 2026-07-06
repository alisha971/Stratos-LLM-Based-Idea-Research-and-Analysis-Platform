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

export type ReportState = {
  title: string;
  content: string;
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
  finalReport: ReportState | null;
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
  | { type: "SET_REPORT_CONTENT"; report: ReportState };

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
  connectionStatus: "idle",
  loginToken: null,
};

export function chatFlowReducer(
  state: ChatFlowState,
  action: ChatFlowAction,
): ChatFlowState {
  switch (action.type) {
    case "SET_LOGIN_TOKEN":
      return {
        ...state,
        loginToken: action.token,
      };
    case "SET_SESSION":
      return {
        ...state,
        sessionId: action.sessionId,
      };
    case "SET_REPORT":
      return {
        ...state,
        reportId: action.reportId,
      };
    case "ADD_MESSAGE":
      return {
        ...state,
        messages: [...state.messages, action.message],
      };
    case "SET_STAGE":
      return {
        ...state,
        stage: action.stage,
      };
    case "SET_CONNECTION_STATUS":
      return {
        ...state,
        connectionStatus: action.status,
      };
    case "ADD_PROGRESS":
      if (state.progressEvents.some((event) => event.id === action.event.id)) {
        return state;
      }
      return {
        ...state,
        progressEvents: [...state.progressEvents, action.event],
      };
    case "SET_SUMMARY":
      return {
        ...state,
        summaryForConsent: action.summary,
      };
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
    case "SET_REPORT_CONTENT":
      return {
        ...state,
        finalReport: action.report,
      };
    default:
      return state;
  }
}

function stringValue(input: unknown): string {
  return typeof input === "string" ? input : "";
}

function buildProgressLabel(eventType: string): string {
  if (eventType === "research_started") return "Research pipeline started";
  if (eventType === "searching_sources") return "Searching high-signal sources";
  if (eventType === "research_done") return "Research completed";
  if (eventType === "research_failed") return "Research failed";
  if (eventType === "scanning_trends") return "Scanning trend signals";
  if (eventType === "trend_ready") return "Trend analysis completed";
  if (eventType === "competitor_discovery") return "Discovering competitors";
  if (eventType === "competitor_done") return "Competitor analysis completed";
  if (eventType === "outline_ready") return "Outline generated";
  if (eventType === "section_done") return "Section ready";
  if (eventType === "report_ready_for_export" || eventType === "export_ready") {
    return "Final report assembled";
  }
  if (eventType === "export_done") return "Export finished";
  return `Event: ${eventType}`;
}

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

  if (
    event.type === "research_started" ||
    event.type === "searching_sources" ||
    event.type === "research_done" ||
    event.type === "research_failed" ||
    event.type === "outline_ready" ||
    event.type === "scanning_trends" ||
    event.type === "trend_ready" ||
    event.type === "competitor_discovery" ||
    event.type === "competitor_done"
  ) {
    actions.push({ type: "SET_STAGE", stage: "researching" });
    actions.push({
      type: "ADD_PROGRESS",
      event: {
        id: `${event.type}-${now}`,
        label: buildProgressLabel(event.type),
        status:
          event.type === "research_done"
            ? "done"
            : event.type.includes("failed")
              ? "error"
              : "running",
        timestamp: now,
      },
    });
  }

  if (event.type === "research_done") {
    actions.push({ type: "SET_STAGE", stage: "streamingSections" });
    actions.push({
      type: "UPSERT_SECTION",
      section: {
        sectionId: `stub-${now}`,
        title: "Section streaming placeholder",
        partialText:
          "Research has finished. Waiting for section writer events. Showing mock flow for now.",
        status: "streaming",
      },
    });
  }

  if (event.type === "section_done" || event.type === "section_chunk") {
    actions.push({ type: "SET_STAGE", stage: "streamingSections" });
    const sectionId = stringValue(payload.section_id) || `section-${now}`;
    actions.push({
      type: "UPSERT_SECTION",
      section: {
        sectionId,
        title: stringValue(payload.title) || "Untitled Section",
        partialText:
          stringValue(payload.text) ||
          stringValue(payload.chunk_text) ||
          "Compiling section content...",
        status: event.type === "section_done" ? "done" : "streaming",
      },
    });
  }

  if (
    event.type === "report_ready_for_export" ||
    event.type === "export_ready" ||
    event.type === "export_done"
  ) {
    actions.push({ type: "SET_STAGE", stage: "reportReady" });
    actions.push({
      type: "SET_REPORT_CONTENT",
      report: {
        title: "Final Market Research Report",
        content:
          "This report view is currently read-only. Full backend assembly output will appear here once connected.",
      },
    });
  }

  if (event.type.includes("failed")) {
    actions.push({ type: "SET_STAGE", stage: "failed" });
  }

  return actions;
}
