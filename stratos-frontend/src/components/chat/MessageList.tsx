import type { ChatMessage } from "@/lib/state/chatFlowStore";

type MessageListProps = {
  messages: ChatMessage[];
};

export function MessageList({ messages }: MessageListProps) {
  if (!messages.length) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-zinc-500">
        Start by describing your idea. I will clarify your intent before research.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {messages.map((message) => (
        <div
          key={message.id}
          className={`max-w-[90%] rounded-2xl px-4 py-3 text-sm leading-6 ${
            message.role === "user"
              ? "ml-auto bg-zinc-200 text-zinc-900"
              : message.role === "assistant"
                ? "bg-zinc-800 text-zinc-100"
                : "mx-auto bg-zinc-700 text-zinc-100"
          }`}
        >
          <p>{message.content}</p>
          {message.meta ? (
            <p className="mt-2 text-xs text-zinc-300/90">{message.meta}</p>
          ) : null}
        </div>
      ))}
    </div>
  );
}
