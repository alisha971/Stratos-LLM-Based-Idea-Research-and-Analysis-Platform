"use client";

import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { LogoMark } from "@/components/brand/Logo";
import { Composer } from "@/components/chat/Composer";
import { MessageList } from "@/components/chat/MessageList";
import { ReportSplitPanel } from "@/components/report/ReportSplitPanel";
import { ClarificationApprovalCard } from "@/components/stages/ClarificationApprovalCard";
import { ResearchProgressTimeline } from "@/components/stages/ResearchProgressTimeline";
import type { ReportView } from "@/lib/api/orchestratorClient";
import {
  ApiError,
  acceptConsent,
  fetchReport,
  fetchSessionStatus,
  getExportFileUrl,
  sendClarificationChat,
  setAuthToken,
  startSession,
} from "@/lib/api/orchestratorClient";
import {
  clearActiveSession,
  clearSession,
  loadActiveSession,
  loadToken,
  storeActiveSession,
} from "@/lib/auth/session";
import {
  chatFlowReducer,
  initialState,
  type ChatFlowAction,
} from "@/lib/state/chatFlowStore";
import type { AppStage } from "@/lib/sse/events";
import { useEventStream } from "@/lib/sse/useEventStream";

function statusToStage(status: string): AppStage {
  switch (status) {
    case "CLARIFYING":
      return "clarifying";
    case "AWAITING_CONSENT":
      return "awaitingConsent";
    case "READY_FOR_RESEARCH":
    case "OUTLINE_GENERATED":
    case "RESEARCH_RUNNING":
      return "researching";
    case "WRITING_SECTIONS":
    case "READY_FOR_ASSEMBLY":
    case "READY_FOR_EXPORT":
      return "streamingSections";
    case "EXPORTED":
      return "reportReady";
    default:
      return "clarifying";
  }
}

function friendlyError(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 402) return "You've reached your free report limit for now.";
    if (err.status === 429) return "You're going a bit fast — please wait a minute and retry.";
    if (err.status === 503) return "We've hit today's capacity. Please try again tomorrow.";
    if (err.status === 401) return "Your session expired. Please sign in again.";
    if (err.status === 422)
      return "Tell me a bit more about your idea — a sentence or two is perfect.";
  }
  return err instanceof Error ? err.message : "Something went wrong.";
}

export function ChatShell() {
  const [state, dispatch] = useReducer(chatFlowReducer, initialState);
  const [token, setToken] = useState<string | null>(null);
  const [booting, setBooting] = useState(true);
  const [busy, setBusy] = useState(false);
  const [reportOpen, setReportOpen] = useState(false);
  const router = useRouter();
  const reportFetched = useRef(false);

  // Auto-open the report panel once the finished report arrives (Claude-artifact
  // behavior). Adjusted during render rather than in an effect so it opens in the
  // same pass the report lands, and only on arrival — the user can still close it.
  const [openedReport, setOpenedReport] = useState<ReportView | null>(null);
  if (state.finalReport && state.finalReport !== openedReport) {
    setOpenedReport(state.finalReport);
    setReportOpen(true);
  }

  const onAction = useCallback((action: ChatFlowAction) => dispatch(action), []);

  useEventStream({ sessionId: state.sessionId, token, onAction });

  // --- Boot: load token, restore any active session (F3.3) ---
  useEffect(() => {
    let cancelled = false;

    async function boot() {
      const stored = loadToken();
      if (!stored) {
        router.replace("/login");
        return;
      }
      setAuthToken(stored);
      if (!cancelled) setToken(stored);

      const { sessionId, reportId } = loadActiveSession();
      if (!sessionId) {
        if (!cancelled) setBooting(false);
        return;
      }

      dispatch({ type: "SET_SESSION", sessionId });
      if (reportId) {
        dispatch({ type: "SET_REPORT", reportId });
      }

      try {
        const status = await fetchSessionStatus(sessionId);
        if (cancelled) return;
        dispatch({ type: "SET_STAGE", stage: statusToStage(status.status) });
        if (status.report_id) {
          dispatch({ type: "SET_REPORT", reportId: status.report_id });
        }
        if (status.status === "AWAITING_CONSENT" && status.clarified_summary) {
          dispatch({ type: "SET_SUMMARY", summary: status.clarified_summary });
        }
        dispatch({
          type: "ADD_MESSAGE",
          message: {
            id: `resume-${Date.now()}`,
            role: "system",
            content: `Resumed your session (${status.status}).`,
          },
        });
      } catch {
        // Stale session id — start fresh.
        clearActiveSession();
        dispatch({ type: "RESET" });
      } finally {
        if (!cancelled) setBooting(false);
      }
    }

    void boot();
    return () => {
      cancelled = true;
    };
  }, [router]);

  // --- Fetch the real report once the pipeline reaches reportReady (F2.3) ---
  useEffect(() => {
    if (
      state.stage === "reportReady" &&
      state.reportId &&
      !state.finalReport &&
      !reportFetched.current
    ) {
      reportFetched.current = true;
      fetchReport(state.reportId)
        .then((report) => dispatch({ type: "SET_FINAL_REPORT", report }))
        .catch((err) => dispatch({ type: "SET_ERROR", error: friendlyError(err) }));
    }
  }, [state.stage, state.reportId, state.finalReport]);

  const sections = useMemo(
    () => state.sectionOrder.map((sectionId) => state.sectionsById[sectionId]),
    [state.sectionOrder, state.sectionsById],
  );

  const canChat = state.stage === "clarifying" && !busy;

  async function handleSend(text: string) {
    dispatch({ type: "SET_ERROR", error: null });
    dispatch({
      type: "ADD_MESSAGE",
      message: { id: `user-${Date.now()}`, role: "user", content: text },
    });

    setBusy(true);
    try {
      if (!state.sessionId) {
        const created = await startSession(text);
        dispatch({ type: "SET_SESSION", sessionId: created.session_id });
        dispatch({ type: "SET_REPORT", reportId: created.report_id });
        storeActiveSession(created.session_id, created.report_id);
      } else {
        await sendClarificationChat(state.sessionId, text);
      }
    } catch (err) {
      dispatch({ type: "SET_ERROR", error: friendlyError(err) });
    } finally {
      setBusy(false);
    }
  }

  async function handleStartResearch() {
    if (!state.sessionId) return;
    dispatch({ type: "SET_ERROR", error: null });
    setBusy(true);
    try {
      await acceptConsent(state.sessionId);
      dispatch({ type: "SET_STAGE", stage: "researching" });
    } catch (err) {
      dispatch({ type: "SET_ERROR", error: friendlyError(err) });
    } finally {
      setBusy(false);
    }
  }

  function handleDownloadPdf() {
    if (state.reportId) {
      window.open(getExportFileUrl(state.reportId), "_blank", "noopener");
    }
  }

  function handleNewReport() {
    clearActiveSession();
    reportFetched.current = false;
    setReportOpen(false);
    dispatch({ type: "RESET" });
  }

  function handleLogout() {
    clearSession();
    clearActiveSession();
    setAuthToken(null);
    router.push("/");
  }

  if (booting) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-paper text-sm text-ink-soft">
        Loading your workspace…
      </div>
    );
  }

  const connected = state.connectionStatus === "connected";
  const hasReportContent = Boolean(state.finalReport) || sections.length > 0;

  return (
    <div className="flex h-screen w-full flex-col bg-paper text-ink">
      <header className="flex items-center justify-between border-b border-rule px-5 py-3">
        <div className="flex items-center gap-4">
          <h1 className="flex items-center gap-2">
            <LogoMark className="h-5 w-5" />
            <span className="font-serif text-lg font-medium tracking-tight">
              Stratos
            </span>
          </h1>
          <span
            className="font-mono text-[11px] uppercase tracking-wider text-ink-faint"
            title={`Live connection: ${state.connectionStatus}`}
          >
            {connected ? "● live" : `○ ${state.connectionStatus}`}
          </span>
        </div>
        <div className="flex items-center gap-4 text-sm">
          <button
            onClick={handleNewReport}
            className="text-ink-soft underline decoration-rule-strong underline-offset-4 hover:text-ink"
          >
            New report
          </button>
          <button
            onClick={handleLogout}
            className="text-ink-soft underline decoration-rule-strong underline-offset-4 hover:text-ink"
          >
            Sign out
          </button>
          <button
            onClick={() => setReportOpen((open) => !open)}
            title={reportOpen ? "Hide report" : "Show report"}
            aria-label={reportOpen ? "Hide report" : "Show report"}
            className={`relative flex h-8 w-8 items-center justify-center border ${
              reportOpen
                ? "border-ink bg-ink text-paper"
                : "border-rule-strong text-ink-soft hover:bg-paper-sunken hover:text-ink"
            }`}
          >
            {/* Panel-right icon */}
            <svg
              width="16"
              height="16"
              viewBox="0 0 16 16"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.3"
            >
              <rect x="1.5" y="2.5" width="13" height="11" />
              <line x1="9.5" y1="2.5" x2="9.5" y2="13.5" />
            </svg>
            {hasReportContent && !reportOpen ? (
              <span className="absolute -right-1 -top-1 h-2 w-2 rounded-full bg-moss" />
            ) : null}
          </button>
        </div>
      </header>

      <main className="flex min-h-0 flex-1">
        {/* Chat column — centered, ChatGPT-style */}
        <section className="flex min-h-0 flex-1 flex-col">
          <div className="min-h-0 flex-1 overflow-y-auto">
            <div className="mx-auto w-full max-w-3xl px-5 py-6">
              <MessageList messages={state.messages} />

              {state.stage === "awaitingConsent" && state.summaryForConsent ? (
                <div className="mt-6">
                  <ClarificationApprovalCard
                    summary={state.summaryForConsent}
                    onEdit={() => dispatch({ type: "SET_STAGE", stage: "clarifying" })}
                    onStartResearch={handleStartResearch}
                  />
                </div>
              ) : null}

              {state.stage === "researching" || state.stage === "streamingSections" ? (
                <div className="mt-6">
                  <ResearchProgressTimeline events={state.progressEvents} />
                </div>
              ) : null}

              {state.stage === "reportReady" && !state.finalReport && !state.error ? (
                <p className="mt-6 text-sm italic text-moss">
                  Report complete. Loading the full document…
                </p>
              ) : null}

              {state.error ? (
                <div className="mt-6 border-l-2 border-rust bg-rust-wash p-3">
                  <p className="text-sm text-rust">{state.error}</p>
                  <button
                    onClick={handleNewReport}
                    className="mt-2 text-xs text-rust underline underline-offset-4 hover:opacity-70"
                  >
                    Start over
                  </button>
                </div>
              ) : null}
            </div>
          </div>

          <Composer
            disabled={!canChat}
            placeholder={
              canChat
                ? "Describe your market idea..."
                : busy
                  ? "Working…"
                  : "Input is disabled during this stage."
            }
            onSend={handleSend}
          />
        </section>

        {/* Report panel — Claude-artifact style: side panel on desktop, overlay on mobile */}
        {reportOpen ? (
          <aside className="fixed inset-0 z-40 lg:static lg:z-auto lg:w-[46%] lg:min-w-[380px] lg:border-l lg:border-rule lg:shadow-[-16px_0_28px_-20px_rgba(33,30,25,0.3)]">
            <ReportSplitPanel
              finalReport={state.finalReport}
              sections={sections}
              onDownloadPdf={handleDownloadPdf}
              downloadDisabled={!state.finalReport}
              onClose={() => setReportOpen(false)}
            />
          </aside>
        ) : null}
      </main>
    </div>
  );
}
