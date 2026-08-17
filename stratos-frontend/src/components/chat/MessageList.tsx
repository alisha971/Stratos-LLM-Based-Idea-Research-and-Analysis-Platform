import { LogoMark } from "@/components/brand/Logo";
import type { ChatMessage } from "@/lib/state/chatFlowStore";

type MessageListProps = {
  messages: ChatMessage[];
};

export function MessageList({ messages }: MessageListProps) {
  if (!messages.length) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center px-6 text-center">
        <div>
          <LogoMark className="mx-auto h-10 w-10" />
          <h2 className="mt-5 font-serif text-3xl font-medium tracking-tight text-ink">
            What are you building?
          </h2>
          <p className="mx-auto mt-3 max-w-sm text-sm leading-relaxed text-ink-faint">
            Describe your idea in a sentence. Stratos asks a few questions,
            then researches the market and writes you a cited report.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {messages.map((message) => {
        if (message.role === "user") {
          return (
            <div key={message.id} className="flex justify-end">
              <div className="max-w-[80%] rounded-3xl rounded-br-md bg-paper-sunken px-4 py-2.5">
                <p className="text-[15px] leading-relaxed text-ink">
                  {message.content}
                </p>
                {message.meta ? (
                  <p className="mt-1.5 text-xs text-ink-faint">{message.meta}</p>
                ) : null}
              </div>
            </div>
          );
        }

        if (message.role === "system") {
          return (
            <p
              key={message.id}
              className="text-center text-xs italic text-ink-faint"
            >
              {message.content}
            </p>
          );
        }

        return (
          <div key={message.id}>
            <p className="text-[15px] leading-relaxed text-ink">
              {message.content}
            </p>
            {message.meta ? (
              <p className="mt-2 text-xs text-ink-faint">{message.meta}</p>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
