"use client";

import type { RunResult } from "@/lib/types";

interface Props {
  cases: RunResult[];
  selected?: string | null;
  onSelect: (caseId: string) => void;
}

export function CaseGrid({ cases, selected, onSelect }: Props) {
  if (!cases.length) {
    return <div className="text-sm text-neutral-500">No cases.</div>;
  }
  return (
    <div className="grid grid-cols-[repeat(auto-fill,minmax(54px,1fr))] gap-2">
      {cases.map((c) => (
        <button
          key={c.case_id}
          onClick={() => onSelect(c.case_id)}
          title={`${c.case_id} — ${c.passed ? "pass" : "fail"} (${c.duration_ms}ms)`}
          className={`aspect-square rounded text-[10px] font-mono leading-tight overflow-hidden px-1 text-white transition-transform hover:scale-105 ${
            c.passed ? "bg-green-600" : "bg-red-600"
          } ${selected === c.case_id ? "ring-2 ring-offset-2 ring-blue-500" : ""}`}
        >
          <span className="block truncate">{c.case_id}</span>
        </button>
      ))}
    </div>
  );
}
