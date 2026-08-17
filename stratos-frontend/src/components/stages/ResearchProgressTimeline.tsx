import type { ProgressEvent } from "@/lib/state/chatFlowStore";

function markerClass(status: ProgressEvent["status"]): string {
  if (status === "done") return "text-moss";
  if (status === "error") return "text-rust";
  return "text-ink-faint";
}

function markerLabel(status: ProgressEvent["status"]): string {
  if (status === "done") return "done";
  if (status === "error") return "failed";
  return "working";
}

export function ResearchProgressTimeline({
  events,
}: {
  events: ProgressEvent[];
}) {
  return (
    <section className="border-t border-rule-strong pt-4">
      <h2 className="font-mono text-[11px] uppercase tracking-wider text-ink-faint">
        Research log
      </h2>
      {events.length ? (
        <ol className="mt-3">
          {events.map((event) => (
            <li
              key={event.id}
              className="flex items-baseline gap-3 border-b border-rule py-2.5 text-sm last:border-b-0"
            >
              <span className="w-16 shrink-0 font-mono text-xs text-ink-faint">
                {new Date(event.timestamp).toLocaleTimeString([], {
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </span>
              <p className="flex-1 text-ink">{event.label}</p>
              <span
                className={`font-mono text-[11px] uppercase tracking-wider ${markerClass(event.status)}`}
              >
                {markerLabel(event.status)}
              </span>
            </li>
          ))}
        </ol>
      ) : (
        <p className="mt-3 font-serif text-sm italic text-ink-faint">
          Setting up — the first entries land in a few seconds.
        </p>
      )}
    </section>
  );
}
