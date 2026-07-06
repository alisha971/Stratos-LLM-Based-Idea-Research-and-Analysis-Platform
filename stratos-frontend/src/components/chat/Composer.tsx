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
    <form onSubmit={handleSubmit} className="w-full border-t border-zinc-800 p-3">
      <div className="flex items-end gap-2 rounded-2xl border border-zinc-700 bg-zinc-900 p-2">
        <textarea
          value={value}
          onChange={(event) => setValue(event.target.value)}
          disabled={disabled || isSending}
          placeholder={placeholder}
          rows={3}
          className="max-h-36 min-h-12 w-full resize-y bg-transparent px-2 py-1 text-sm text-zinc-100 outline-none placeholder:text-zinc-500"
        />
        <button
          type="submit"
          disabled={disabled || isSending || !value.trim()}
          className="rounded-xl bg-zinc-100 px-4 py-2 text-xs font-semibold text-zinc-900 disabled:cursor-not-allowed disabled:opacity-40"
        >
          Send
        </button>
      </div>
    </form>
  );
}
