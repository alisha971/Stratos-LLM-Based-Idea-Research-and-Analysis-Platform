"use client";

import { FormEvent, useState } from "react";

type ComposerProps = {
  disabled?: boolean;
  placeholder?: string;
  onSend: (text: string) => Promise<void> | void;
};

export function Composer({
  disabled = false,
  placeholder = "Describe your idea...",
  onSend,
}: ComposerProps) {
  const [value, setValue] = useState("");
  const [isSending, setIsSending] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const text = value.trim();
    if (!text || disabled || isSending) {
      return;
    }

    setIsSending(true);
    try {
      await onSend(text);
      setValue("");
    } finally {
      setIsSending(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="w-full px-5 pb-4 pt-2">
      <div className="mx-auto w-full max-w-3xl">
        <div className="shadow-lift flex items-end gap-2 rounded-3xl border border-rule-strong bg-paper-raised py-2 pl-5 pr-2 transition-colors focus-within:border-ink">
          <textarea
            value={value}
            onChange={(event) => setValue(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void handleSubmit(event);
              }
            }}
            disabled={disabled || isSending}
            placeholder={placeholder}
            rows={2}
            className="max-h-40 min-h-10 w-full resize-none bg-transparent py-2 text-[15px] leading-relaxed text-ink outline-none placeholder:text-ink-faint disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={disabled || isSending || !value.trim()}
            aria-label="Send"
            className="mb-1 flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-ink text-paper hover:bg-moss-deep disabled:cursor-not-allowed disabled:opacity-25"
          >
            <svg
              width="16"
              height="16"
              viewBox="0 0 16 16"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M8 13V3" />
              <path d="M3.5 7.5 8 3l4.5 4.5" />
            </svg>
          </button>
        </div>
        <p className="mt-2 text-center text-xs text-ink-faint">
          Reports are AI-written from public sources — every claim is cited.
        </p>
      </div>
    </form>
  );
}
