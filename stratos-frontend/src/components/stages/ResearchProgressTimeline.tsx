import type { ProgressEvent } from "@/lib/state/chatFlowStore";

type ResearchProgressTimelineProps = {
  events: ProgressEvent[];
};

function marker(status: ProgressEvent["status"]): string {
  if (status === "done") return "Done";
  if (status === "error") return "Fail";
  return "Run";
}

export function ResearchProgressTimeline({ events }: ResearchProgressTimelineProps) {
  return (
    <section className="rounded-2xl border border-zinc-700 bg-zinc-900 p-5">
      <h2 className="text-base font-semibold text-zinc-100">Research progress</h2>
      {events.length ? (
        <ol className="mt-3 space-y-3">
          {events.map((event) => (
            <li key={event.id} className="flex items-start gap-3 text-sm">
              <span className="rounded-md bg-zinc-700 px-2 py-1 text-[10px] text-zinc-200">
                {marker(event.status)}
              </span>
              <div>
                <p className="text-zinc-200">{event.label}</p>
                <p className="text-xs text-zinc-500">
                  {new Date(event.timestamp).toLocaleTimeString()}
                </p>
              </div>
            </li>
          ))}
        </ol>
      ) : (
        <p className="mt-3 text-sm text-zinc-400">
          Waiting for backend progress events...
        </p>
      )}
    </section>
  );
}
