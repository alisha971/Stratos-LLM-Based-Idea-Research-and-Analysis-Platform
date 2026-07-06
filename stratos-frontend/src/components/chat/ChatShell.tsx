"use client";

import { useCallback, useMemo, useReducer, useState } from "react";
import { useRouter } from "next/navigation";

import { Composer } from "@/components/chat/Composer";
import { MessageList } from "@/components/chat/MessageList";
import { ReportSplitPanel } from "@/components/report/ReportSplitPanel";
import { BackendSequenceMap } from "@/components/stages/BackendSequenceMap";
import { ClarificationApprovalCard } from "@/components/stages/ClarificationApprovalCard";
import { ResearchProgressTimeline } from "@/components/stages/ResearchProgressTimeline";
import {
  acceptConsent,
  fetchSessionStatus,
  sendClarificationChat,
  startSession,
} from "@/lib/api/orchestratorClient";
import {
  chatFlowReducer,
  initialState,
  type ChatFlowAction,
} from "@/lib/state/chatFlowStore";
import { useEventStream } from "@/lib/sse/useEventStream";

export function ChatShell() {
  const [state, dispatch] = useReducer(chatFlowReducer, initialState);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const router = useRouter();

  useEventStream({
    enabled: Boolean(state.loginToken),
    onAction: useCallback((action: ChatFlowAction) => dispatch(action), []),
  });

  const sections = useMemo(
    () => state.sectionOrder.map((sectionId) => state.sectionsById[sectionId]),
    [state.sectionOrder, state.sectionsById],
  );

  const canChat = state.stage === "clarifying";

  async function handleSend(text: string) {
    setError(null);
    const now = new Date().toISOString();
    dispatch({
      type: "ADD_MESSAGE",
      message: {
        id: `user-${now}`,
        role: "user",
        content: text,
      },
    });

    try {
      if (!state.sessionId) {
        const created = await startSession(text);
        dispatch({ type: "SET_SESSION", sessionId: created.session_id });
      } else {
        await sendClarificationChat(state.sessionId, text);
      }
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to process your request.",
      );
    }
  }

  async function handleStartResearch() {
    if (!state.sessionId) {
      return;
    }
    setError(null);
    try {
      await acceptConsent(state.sessionId);
      dispatch({ type: "SET_STAGE", stage: "researching" });
      dispatch({
        type: "ADD_PROGRESS",
        event: {
          id: `consent-${new Date().toISOString()}`,
          label: "Consent accepted. Starting outline and research.",
          status: "running",
          timestamp: new Date().toISOString(),
        },
      });
      dispatch({
        type: "ADD_PROGRESS",
        event: {
          id: `mock-section-${new Date().toISOString()}`,
          label: "Section writer stage (stubbed until backend emits section events)",
          status: "running",
          timestamp: new Date().toISOString(),
        },
      });
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Failed to accept clarification consent.",
      );
    }
  }

  async function handleLoadFromStatus() {
    if (!state.sessionId) {
      return;
    }
    setError(null);
    try {
      const status = await fetchSessionStatus(state.sessionId);
      dispatch({ type: "SET_REPORT", reportId: status.report_id });
      dispatch({
        type: "ADD_MESSAGE",
        message: {
          id: `sync-${new Date().toISOString()}`,
          role: "system",
          content: `Recovered session state: ${status.session_state}`,
        },
      });
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Failed to recover session state.",
      );
    }
  }

  function handleLogin() {
    const token = `demo-token-${Date.now()}`;
    dispatch({ type: "SET_LOGIN_TOKEN", token });
    dispatch({
      type: "ADD_MESSAGE",
      message: {
        id: `welcome-${new Date().toISOString()}`,
        role: "assistant",
        content:
          "You are signed in. Share your startup/market idea and I will begin clarification.",
      },
    });
  }

  function handleLogout() {
    dispatch({ type: "SET_LOGIN_TOKEN", token: null });
    router.push("/login");
  }

  function handleDownloadPdf() {
    setInfo("PDF export is not yet enabled. Backend export endpoint is stubbed.");
  }

  if (!state.loginToken) {
    return (
      <div className="mx-auto flex min-h-screen w-full max-w-3xl items-center justify-center px-4">
        <section className="w-full rounded-2xl border border-zinc-700 bg-zinc-900 p-6">
          <h1 className="text-2xl font-semibold text-zinc-100">Stratos Login</h1>
          <p className="mt-3 text-sm text-zinc-400">
            This is a frontend login stub aligned to the backend auth flow. Use this
            temporary button to continue.
          </p>
          <button
            onClick={handleLogin}
            className="mt-5 rounded-xl bg-white px-4 py-2 text-sm font-semibold text-zinc-900"
          >
            Continue with Google (Stub)
          </button>
        </section>
      </div>
    );
  }

  return (
    <div className="h-screen w-full bg-black text-zinc-100">
      <header className="flex items-center justify-between border-b border-zinc-800 px-4 py-3">
        <h1 className="text-sm font-semibold">Stratos Research Copilot</h1>
        <div className="flex items-center gap-2">
          <span className="text-xs text-zinc-400">
            SSE: {state.connectionStatus}
          </span>
          <button
            onClick={handleLoadFromStatus}
            className="rounded-lg border border-zinc-700 px-3 py-1 text-xs hover:bg-zinc-900"
          >
            Sync status
          </button>
          <button
            onClick={handleLogout}
            className="rounded-lg border border-zinc-700 px-3 py-1 text-xs hover:bg-zinc-900"
          >
            Logout
          </button>
        </div>
      </header>

      <main className="grid h-[calc(100vh-52px)] grid-cols-1 gap-3 p-3 lg:grid-cols-2">
        <section className="flex min-h-0 flex-col rounded-2xl border border-zinc-800 bg-zinc-950">
          <div className="min-h-0 flex-1 overflow-y-auto p-3">
            <BackendSequenceMap />
            <MessageList messages={state.messages} />
            {state.stage === "awaitingConsent" && state.summaryForConsent ? (
              <div className="mt-4">
                <ClarificationApprovalCard
                  summary={state.summaryForConsent}
                  onEdit={() => dispatch({ type: "SET_STAGE", stage: "clarifying" })}
                  onStartResearch={handleStartResearch}
                />
              </div>
            ) : null}
            {state.stage === "researching" || state.stage === "streamingSections" ? (
              <div className="mt-4">
                <ResearchProgressTimeline events={state.progressEvents} />
              </div>
            ) : null}
            {state.stage === "streamingSections" && !sections.length ? (
              <p className="mt-4 text-sm text-zinc-500">
                Compiling sections...
              </p>
            ) : null}
            {error ? <p className="mt-4 text-sm text-red-400">{error}</p> : null}
            {info ? <p className="mt-4 text-sm text-blue-300">{info}</p> : null}
          </div>
          <Composer
            disabled={!canChat}
            placeholder={
              canChat
                ? "Describe your market idea..."
                : "Input is disabled during this stage."
            }
            onSend={handleSend}
          />
        </section>

        <ReportSplitPanel
          finalReport={state.finalReport}
          sections={sections}
          onDownloadPdf={handleDownloadPdf}
        />
      </main>
    </div>
  );
}
