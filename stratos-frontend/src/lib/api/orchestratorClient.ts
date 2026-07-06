const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export type StartSessionResponse = {
  session_id: string;
  state: string;
};

export type ChatResponse = {
  session_id: string;
  state: string;
  user_message: string;
};

export type ConsentResponse = {
  session_id: string;
  status: string;
  message: string;
};

export type StatusResponse = {
  session_id: string;
  report_id: string;
  session_state: string;
  report_status: string;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed: ${response.status}`);
  }

  return (await response.json()) as T;
}

export async function startSession(
  ideaInput: string,
): Promise<StartSessionResponse> {
  return request<StartSessionResponse>("/orchestrate/orchestrate/start-session", {
    method: "POST",
    body: JSON.stringify({
      idea_input: ideaInput,
    }),
  });
}

export async function sendClarificationChat(
  sessionId: string,
  userInput: string,
): Promise<ChatResponse> {
  return request<ChatResponse>("/orchestrate/orchestrate/clarification/chat", {
    method: "POST",
    body: JSON.stringify({
      session_id: sessionId,
      user_input: userInput,
    }),
  });
}

export async function acceptConsent(sessionId: string): Promise<ConsentResponse> {
  return request<ConsentResponse>(
    "/orchestrate/orchestrate/clarification/accept-consent",
    {
      method: "POST",
      body: JSON.stringify({
        session_id: sessionId,
      }),
    },
  );
}

export async function fetchSessionStatus(
  sessionId: string,
): Promise<StatusResponse> {
  return request<StatusResponse>(`/orchestrate/orchestrate/status/${sessionId}`);
}

export function streamUrl(): string {
  return `${API_BASE_URL}/stream/events`;
}
