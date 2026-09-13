import type { ReportView, Verdict } from "@/lib/api/orchestratorClient";
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
  // null = not ready yet. Once state.stage reaches "streamingSections" the
  // UI reserves the verdict's slot and shows a pending state until this
  // arrives (verdict_ready) -- see ReportSplitPanel.
  verdict: Verdict | null;
  unresolvedGaps: string[];
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
  | { type: "SET_VERDICT"; verdict: Verdict; unresolvedGaps: string[] }
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
  verdict: null,
  unresolvedGaps: [],
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
    case "SET_VERDICT":
      return { ...state, verdict: action.verdict, unresolvedGaps: action.unresolvedGaps };
    case "SET_FINAL_REPORT":
      // Backfills verdict/unresolvedGaps from the fetched report too --
      // not just from the live verdict_ready SSE event. A session resumed
      // after the verdict already landed (page reload, reconnect) never
      // sees that event fire again; fetchReport's response is the only
      // way it would otherwise learn the verdict exists.
      return {
        ...state,
        finalReport: action.report,
        verdict: action.report.verdict ?? state.verdict,
        unresolvedGaps: action.report.unresolved_gaps ?? state.unresolvedGaps,
      };
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
    scanning_competitors: "Scanning competitor landscape",
    competitor_ready: "Competitor analysis completed",
    competitor_failed: "Competitor scan failed (continuing without competitors)",
    section_writing_started: "Writing sections",
    sections_done: "All sections written",
    verdict_started: "Weighing the evidence",
    verdict_ready: "Verdict reached",
    report_assembled: "Assembling report",
    export_done: "Export finished",
  };
  return labels[eventType] ?? `Event: ${eventType}`;
}

// Events strictly BEFORE section writing starts -- these are the only ones
// that should push stage back to "researching". Previously
// RESEARCH_PROGRESS_EVENTS did this for every member including
// sections_done/report_assembled, which fire well after
// section_writing_started already moved the stage to "streamingSections" --
// regressing it back to "researching" on screen for events that are
// actually later in the pipeline. Fixed here while adding verdict_started/
// verdict_ready, which would otherwise have extended the same bug.
const PRE_WRITING_PROGRESS_EVENTS = new Set([
  "research_started",
  "searching_sources",
  "research_done",
  "research_failed",
  "outline_ready",
  "outline_accepted",
  "scanning_trends",
  "trend_ready",
  "trend_failed",
  "scanning_competitors",
  "competitor_ready",
  "competitor_failed",
]);

// Everything that produces a timeline log entry -- a superset of
// PRE_WRITING_PROGRESS_EVENTS, including milestones after writing starts.
const RESEARCH_PROGRESS_EVENTS = new Set([
  ...PRE_WRITING_PROGRESS_EVENTS,
  "section_writing_started",
  "sections_done",
  "verdict_started",
  "verdict_ready",
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
    if (PRE_WRITING_PROGRESS_EVENTS.has(event.type)) {
      actions.push({ type: "SET_STAGE", stage: "researching" });
    }
    actions.push({
      type: "ADD_PROGRESS",
      event: {
        id: `${event.type}-${now}`,
        label: buildProgressLabel(event.type),
        // "_ready" events (trend_ready, competitor_ready, outline_ready,
        // verdict_ready) previously fell through to "running" forever --
        // their label said "completed"/"reached" next to a status still
        // reading "working". Fixed alongside adding verdict_ready, which
        // would otherwise have been a new instance of the same bug.
        status:
          event.type.endsWith("_done") || event.type.endsWith("_ready")
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

  // verdict_ready carries the full prose (see verdict_worker.py) so the
  // card can render immediately -- it does not wait for export_done, the
  // way the rest of the finished report currently does.
  if (event.type === "verdict_ready") {
    const verdictValue = stringValue(payload.verdict);
    if (verdictValue === "build" || verdictValue === "reshape" || verdictValue === "walk_away") {
      actions.push({
        type: "SET_VERDICT",
        verdict: {
          verdict: verdictValue,
          holding: stringValue(payload.holding) || null,
          flip_condition: stringValue(payload.flip_condition) || null,
          confidence:
            (payload.confidence as "high" | "medium" | "low" | undefined) ?? null,
          payload: {
            case_for_prose: stringValue(payload.case_for_prose) || undefined,
            case_against_prose: stringValue(payload.case_against_prose) || undefined,
            which_won: stringValue(payload.which_won) || undefined,
          },
        },
        unresolvedGaps: Array.isArray(payload.unresolved_gaps)
          ? payload.unresolved_gaps.filter((gap): gap is string => typeof gap === "string")
          : [],
      });
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
    // trend_failed and competitor_failed are non-fatal: the pipeline
    // continues without trend items / competitors. verdict_failed is
    // non-fatal too (backend Stage 4d) -- sections are already fully
    // written by the time the verdict runs, so a missing verdict must not
    // be shown as a broken report.
    const NON_FATAL_FAILURES = new Set([
      "trend_failed",
      "competitor_failed",
      "verdict_failed",
    ]);
    const errorMessage = stringValue(payload.error) || `${event.type}`;
    if (!NON_FATAL_FAILURES.has(event.type)) {
      actions.push({ type: "SET_ERROR", error: errorMessage });
      actions.push({ type: "SET_STAGE", stage: "failed" });
    }
  }

  return actions;
}
