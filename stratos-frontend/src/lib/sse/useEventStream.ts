"use client";

import { useEffect, useRef } from "react";

import { streamUrl } from "@/lib/api/orchestratorClient";
import { parseEventData } from "@/lib/sse/events";
import { eventToActions, type ChatFlowAction } from "@/lib/state/chatFlowStore";

type UseEventStreamArgs = {
  enabled: boolean;
  onAction: (action: ChatFlowAction) => void;
};

export function useEventStream({ enabled, onAction }: UseEventStreamArgs): void {
  const seenEvents = useRef<Set<string>>(new Set());

  useEffect(() => {
    if (!enabled) {
      return;
    }

    onAction({ type: "SET_CONNECTION_STATUS", status: "connected" });
    const source = new EventSource(streamUrl());

    source.onmessage = (message) => {
      const parsed = parseEventData(message.data);
      if (!parsed) {
        return;
      }

      const dedupeKey = `${parsed.type}:${JSON.stringify(parsed.payload)}`;
      if (seenEvents.current.has(dedupeKey)) {
        return;
      }
      seenEvents.current.add(dedupeKey);

      const actions = eventToActions(parsed);
      for (const action of actions) {
        onAction(action);
      }
    };

    source.onerror = () => {
      onAction({ type: "SET_CONNECTION_STATUS", status: "disconnected" });
      source.close();
      setTimeout(() => {
        onAction({ type: "SET_CONNECTION_STATUS", status: "connected" });
      }, 1200);
    };

    return () => {
      source.close();
      onAction({ type: "SET_CONNECTION_STATUS", status: "idle" });
    };
  }, [enabled, onAction]);
}
