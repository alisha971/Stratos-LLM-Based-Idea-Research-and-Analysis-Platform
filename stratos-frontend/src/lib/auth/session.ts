"use client";

import type { AuthUser } from "@/lib/api/orchestratorClient";

// MVP storage tradeoff (documented, per F3.1): the JWT lives in localStorage
// (readable by JS — accepted XSS risk for a small beta) plus a non-httpOnly
// cookie so the Next.js middleware can gate /app routes server-side. Premium
// F3.1 replaces this with an httpOnly-cookie route handler.
const TOKEN_KEY = "stratos_token";
const USER_KEY = "stratos_user";
export const COOKIE_NAME = "stratos_token";

export function storeSession(token: string, user: AuthUser | null): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(TOKEN_KEY, token);
  if (user) {
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  }
  // Session cookie (cleared when browser closes); Lax + Secure in prod.
  const secure = window.location.protocol === "https:" ? "; Secure" : "";
  document.cookie = `${COOKIE_NAME}=${encodeURIComponent(token)}; Path=/; SameSite=Lax${secure}`;
}

export function loadToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function loadUser(): AuthUser | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AuthUser;
  } catch {
    return null;
  }
}

export function clearSession(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  document.cookie = `${COOKIE_NAME}=; Path=/; Max-Age=0; SameSite=Lax`;
}

// --- Session/report resume state (F3.3) ---
const ACTIVE_SESSION_KEY = "stratos_active_session";
const ACTIVE_REPORT_KEY = "stratos_active_report";

export function storeActiveSession(sessionId: string, reportId: string | null): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(ACTIVE_SESSION_KEY, sessionId);
  if (reportId) {
    localStorage.setItem(ACTIVE_REPORT_KEY, reportId);
  }
}

export function loadActiveSession(): { sessionId: string | null; reportId: string | null } {
  if (typeof window === "undefined") return { sessionId: null, reportId: null };
  return {
    sessionId: localStorage.getItem(ACTIVE_SESSION_KEY),
    reportId: localStorage.getItem(ACTIVE_REPORT_KEY),
  };
}

export function clearActiveSession(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(ACTIVE_SESSION_KEY);
  localStorage.removeItem(ACTIVE_REPORT_KEY);
}
