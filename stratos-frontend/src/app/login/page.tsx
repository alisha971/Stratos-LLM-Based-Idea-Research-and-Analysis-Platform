"use client";

import Link from "next/link";
import Script from "next/script";

import { Logo } from "@/components/brand/Logo";
import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { loginWithGoogle, setAuthToken } from "@/lib/api/orchestratorClient";
import { storeSession } from "@/lib/auth/session";

const GOOGLE_CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID ?? "";

type CredentialResponse = { credential: string };

// Minimal GSI typing (no official types in this project).
declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (config: {
            client_id: string;
            callback: (response: CredentialResponse) => void;
          }) => void;
          renderButton: (
            parent: HTMLElement,
            options: Record<string, unknown>,
          ) => void;
        };
      };
    };
  }
}

export default function LoginPage() {
  const router = useRouter();
  const buttonRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [scriptReady, setScriptReady] = useState(false);

  const handleCredential = useCallback(
    async (response: CredentialResponse) => {
      setBusy(true);
      setError(null);
      try {
        const result = await loginWithGoogle(response.credential);
        setAuthToken(result.access_token);
        storeSession(result.access_token, result.user);
        router.push("/app");
      } catch {
        setError("Sign-in failed. Please try again.");
        setBusy(false);
      }
    },
    [router],
  );

  useEffect(() => {
    if (!scriptReady || !GOOGLE_CLIENT_ID || !window.google || !buttonRef.current) {
      return;
    }
    window.google.accounts.id.initialize({
      client_id: GOOGLE_CLIENT_ID,
      callback: handleCredential,
    });
    window.google.accounts.id.renderButton(buttonRef.current, {
      theme: "outline",
      size: "large",
      text: "continue_with",
      shape: "pill",
    });
  }, [scriptReady, handleCredential]);

  function handleDevLogin() {
    // Local-only shortcut: works when the backend runs with DEV_AUTH_BYPASS=true.
    setAuthToken("dev");
    storeSession("dev", {
      id: "dev-user",
      email: "dev@stratos.local",
      name: "Dev User",
      plan: "free",
    });
    router.push("/app");
  }

  return (
    <main className="flex min-h-screen flex-col bg-paper px-6 text-ink">
      {GOOGLE_CLIENT_ID ? (
        <Script
          src="https://accounts.google.com/gsi/client"
          strategy="afterInteractive"
          onLoad={() => setScriptReady(true)}
        />
      ) : null}

      <header className="mx-auto w-full max-w-4xl border-b border-rule-strong py-6">
        <Link href="/">
          <Logo />
        </Link>
      </header>

      <div className="flex flex-1 items-center justify-center py-16">
        <section className="w-full max-w-sm">
          <h1 className="font-serif text-3xl font-medium tracking-tight">
            Sign in
          </h1>
          <p className="mt-3 text-sm leading-relaxed text-ink-soft">
            Your first cited market report takes about ten minutes. Free while
            in beta.
          </p>

          {GOOGLE_CLIENT_ID ? (
            <div className="mt-8 flex justify-start" ref={buttonRef} />
          ) : (
            <p className="mt-8 border-l-2 border-rust bg-rust-wash p-3 text-xs leading-relaxed text-rust">
              Google sign-in is not configured (set NEXT_PUBLIC_GOOGLE_CLIENT_ID).
              Use the dev button below for local testing.
            </p>
          )}

          <button
            onClick={handleDevLogin}
            disabled={busy}
            className="mt-4 w-full border border-rule-strong px-4 py-2.5 text-sm text-ink hover:bg-paper-sunken disabled:opacity-40"
          >
            Continue in dev mode
          </button>

          {busy ? (
            <p className="mt-4 text-sm text-ink-soft">Signing you in…</p>
          ) : null}
          {error ? <p className="mt-4 text-sm text-rust">{error}</p> : null}
        </section>
      </div>
    </main>
  );
}
