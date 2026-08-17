"use client";

import { useEffect, useRef } from "react";

import { streamUrl } from "@/lib/api/orchestratorClient";
import { parseEventData } from "@/lib/sse/events";
import { eventToActions, type ChatFlowAction } from "@/lib/state/chatFlowStore";

type UseEventStreamArgs = {
  sessionId: string | null;
  token: string | null;
  onAction: (action: ChatFlowAction) => void;
};

const MAX_BACKOFF = 30_000;

export function useEventStream({
  sessionId,
  token,
  onAction,
}: UseEventStreamArgs): void {
  const seenEvents = useRef<Set<string>>(new Set());

  useEffect(() => {
    if (!sessionId || !token) {
      return;
    }

    let source: EventSource | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let backoff = 1_000;
    let closed = false;

    const connect = () => {
      if (closed) {
        return;
      }
      source = new EventSource(streamUrl(sessionId, token));

      source.onopen = () => {
        onAction({ type: "SET_CONNECTION_STATUS", status: "connected" });
      };

      source.onmessage = (message) => {
        // Reset backoff on any successful message.
        backoff = 1_000;
        onAction({ type: "SET_CONNECTION_STATUS", status: "connected" });

        const parsed = parseEventData(message.data);
        if (!parsed) {
          return;
        }

        // Defense-in-depth: backend already filters by session, but drop any
        // event that doesn't match this session just in case.
        const payloadSession =
          typeof parsed.payload.session_id === "string"
            ? parsed.payload.session_id
            : null;
        if (payloadSession && payloadSession !== sessionId) {
          return;
        }

        const dedupeKey = `${parsed.type}:${JSON.stringify(parsed.payload)}`;
        if (seenEvents.current.has(dedupeKey)) {
          return;
        }
        seenEvents.current.add(dedupeKey);

        for (const action of eventToActions(parsed)) {
          onAction(action);
        }
      };

      source.onerror = () => {
        onAction({ type: "SET_CONNECTION_STATUS", status: "disconnected" });
        source?.close();
        source = null;
        if (closed) {
          return;
        }
        reconnectTimer = setTimeout(connect, backoff);
        backoff = Math.min(backoff * 2, MAX_BACKOFF);
      };
    };

    connect();

    return () => {
      closed = true;
      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
      }
      source?.close();
      onAction({ type: "SET_CONNECTION_STATUS", status: "idle" });
    };
  }, [sessionId, token, onAction]);
}
