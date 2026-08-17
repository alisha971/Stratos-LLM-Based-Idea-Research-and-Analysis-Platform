const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

// --- Auth token (module-level; set after login, cleared on logout) ---
let authToken: string | null = null;

export function setAuthToken(token: string | null): void {
  authToken = token;
}

export function getAuthToken(): string | null {
  return authToken;
}

// --- Response types (doc 05 contract) ---
export type StartSessionResponse = {
  session_id: string;
  report_id: string;
  status: string;
  message: string;
};

export type ChatResponse = {
  session_id: string;
  status: string;
};

export type ConsentResponse = {
  session_id: string;
  status: string;
  message: string;
};

export type StatusResponse = {
  session_id: string;
  status: string;
  idea_description: string | null;
  clarified_summary: string | null;
  report_id: string | null;
  report_status: string | null;
};

export type Citation = {
  marker: string;
  url: string | null;
  domain: string | null;
  title: string | null;
};

export type ReportChunk = {
  chunk_id: string;
  order_index: number;
  text: string;
  citations: Citation[];
};

export type ReportSection = {
  section_id: string;
  title: string;
  order_index: number;
  chunks: ReportChunk[];
};

export type ReportView = {
  report_id: string;
  status: string;
  title: string;
  sections: ReportSection[];
};

export type AuthUser = {
  id: string;
  email: string;
  name: string | null;
  plan: string;
};

export type GoogleLoginResponse = {
  access_token: string;
  token_type: string;
  user: AuthUser;
};

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((init?.headers as Record<string, string>) ?? {}),
  };
  if (authToken) {
    headers.Authorization = `Bearer ${authToken}`;
  }

  const response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });

  if (!response.ok) {
    const message = await response.text();
    throw new ApiError(response.status, message || `Request failed: ${response.status}`);
  }

  return (await response.json()) as T;
}

export async function loginWithGoogle(
  idToken: string,
): Promise<GoogleLoginResponse> {
  return request<GoogleLoginResponse>("/auth/google", {
    method: "POST",
    body: JSON.stringify({ id_token: idToken }),
  });
}

export async function startSession(
  ideaDescription: string,
): Promise<StartSessionResponse> {
  return request<StartSessionResponse>("/orchestrate/start-session", {
    method: "POST",
    body: JSON.stringify({ idea_description: ideaDescription }),
  });
}

export async function sendClarificationChat(
  sessionId: string,
  message: string,
): Promise<ChatResponse> {
  return request<ChatResponse>("/orchestrate/clarification/chat", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId, message }),
  });
}

export async function acceptConsent(sessionId: string): Promise<ConsentResponse> {
  return request<ConsentResponse>("/orchestrate/clarification/accept-consent", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId }),
  });
}

export async function fetchSessionStatus(
  sessionId: string,
): Promise<StatusResponse> {
  return request<StatusResponse>(`/orchestrate/status/${sessionId}`);
}

export async function fetchReport(reportId: string): Promise<ReportView> {
  return request<ReportView>(`/reports/${reportId}`);
}

export function getExportFileUrl(reportId: string): string {
  return `${API_BASE_URL}/exports/${reportId}/file`;
}

export function streamUrl(sessionId: string, token: string): string {
  return `${API_BASE_URL}/stream/events/${sessionId}?token=${encodeURIComponent(token)}`;
}
