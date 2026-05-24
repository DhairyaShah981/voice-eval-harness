"use client";

import type { RunResult, TranscriptEvent } from "@/lib/types";

interface Props {
  runCase: RunResult | null;
  onClose: () => void;
}

function roleColor(role: TranscriptEvent["role"]): string {
  switch (role) {
    case "user":
      return "bg-blue-100 text-blue-900";
    case "agent":
      return "bg-emerald-100 text-emerald-900";
    case "tool":
      return "bg-amber-100 text-amber-900";
    default:
      return "bg-neutral-100 text-neutral-700";
  }
}

export function TranscriptDrawer({ runCase, onClose }: Props) {
  if (!runCase) return null;
  return (
    <aside className="fixed inset-y-0 right-0 z-20 w-full max-w-xl overflow-y-auto border-l border-neutral-200 bg-white shadow-xl">
      <div className="sticky top-0 flex items-center justify-between border-b border-neutral-200 bg-white px-5 py-3">
        <div>
          <h2 className="font-mono text-sm font-semibold">{runCase.case_id}</h2>
          <p className="text-xs text-neutral-500">
            {runCase.passed ? "PASS" : "FAIL"} · {runCase.duration_ms}ms · $
            {runCase.cost_usd.toFixed(4)}
          </p>
        </div>
        <button
          onClick={onClose}
          className="rounded px-2 py-1 text-sm text-neutral-500 hover:bg-neutral-100"
          aria-label="Close"
        >
          ×
        </button>
      </div>

      <div className="px-5 py-4 space-y-4">
        {runCase.error && (
          <div className="rounded border border-red-200 bg-red-50 p-3 text-xs text-red-800">
            <div className="font-semibold mb-1">Error</div>
            <pre className="whitespace-pre-wrap">{runCase.error}</pre>
          </div>
        )}

        <section>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-neutral-500">
            Assertions
          </h3>
          {runCase.assertion_results.length === 0 ? (
            <p className="text-xs text-neutral-400">none</p>
          ) : (
            <ul className="space-y-1.5">
              {runCase.assertion_results.map((a, i) => (
                <li
                  key={i}
                  className="flex items-start gap-2 rounded border border-neutral-200 p-2 text-xs"
                >
                  <span
                    className={`mt-0.5 inline-block h-2 w-2 rounded-full ${
                      a.passed ? "bg-green-500" : "bg-red-500"
                    }`}
                  />
                  <div>
                    <div className="font-mono">{a.kind}</div>
                    {a.detail && (
                      <div className="text-neutral-600">{a.detail}</div>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-neutral-500">
            Transcript
          </h3>
          {runCase.transcript.length === 0 ? (
            <p className="text-xs text-neutral-400">empty</p>
          ) : (
            <ol className="space-y-2">
              {runCase.transcript.map((ev, i) => (
                <li
                  key={i}
                  className={`rounded px-3 py-2 text-xs ${roleColor(ev.role)}`}
                >
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="font-mono font-semibold uppercase">
                      {ev.role}
                    </span>
                    <span className="text-[10px] opacity-60">{ev.ts_ms}ms</span>
                  </div>
                  {ev.text && (
                    <p className="mt-1 whitespace-pre-wrap">{ev.text}</p>
                  )}
                  {ev.tool_name && (
                    <p className="mt-1 font-mono">
                      <span className="opacity-60">tool:</span> {ev.tool_name}
                      {ev.tool_args && (
                        <span className="opacity-60">
                          {" "}
                          {JSON.stringify(ev.tool_args)}
                        </span>
                      )}
                    </p>
                  )}
                </li>
              ))}
            </ol>
          )}
        </section>
      </div>
    </aside>
  );
}
