export type BackendEventType =
  | "session_created"
  | "clarification_started"
  | "clarification_update"
  | "clarification_ready"
  | "clarification_consent_requested"
  | "clarification_completed"
  | "outline_ready"
  | "outline_accepted"
  | "research_started"
  | "searching_sources"
  | "research_done"
  | "research_failed"
  | "scanning_trends"
  | "trend_ready"
  | "competitor_discovery"
  | "competitor_done"
  | "section_done"
  | "section_chunk"
  | "report_ready_for_export"
  | "export_done"
  | "export_ready"
  | "unknown";

export type StreamEnvelope = {
  type: BackendEventType | string;
  payload: Record<string, unknown>;
};

export type AppStage =
  | "clarifying"
  | "awaitingConsent"
  | "researching"
  | "streamingSections"
  | "reportReady"
  | "failed";

export function parseEventData(data: string): StreamEnvelope | null {
  try {
    const parsed = JSON.parse(data) as StreamEnvelope;
    if (!parsed || typeof parsed !== "object") {
      return null;
    }
    if (typeof parsed.type !== "string") {
      return null;
    }
    return {
      type: parsed.type,
      payload:
        parsed.payload && typeof parsed.payload === "object" ? parsed.payload : {},
    };
  } catch {
    return null;
  }
}
