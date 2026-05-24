"use client";

import { useCallback, useState } from "react";
import type { SuiteResult, RunRow } from "@/lib/types";

interface Props {
  /** Called with the parsed report after a successful drop/upload. */
  onParsed: (report: SuiteResult, asRow: RunRow) => void;
}

function suiteHashOf(report: SuiteResult): string {
  // Cheap stable-ish hash for local mode (no crypto dependency).
  const s = report.cases.map((c) => c.case_id).join("|");
  let h = 0;
  for (let i = 0; i < s.length; i++) {
    h = (h << 5) - h + s.charCodeAt(i);
    h |= 0;
  }
  return `local-${Math.abs(h).toString(16)}`;
}

export function UploadDropzone({ onParsed }: Props) {
  const [error, setError] = useState<string | null>(null);
  const [hover, setHover] = useState(false);

  const ingest = useCallback(
    async (file: File) => {
      setError(null);
      try {
        const text = await file.text();
        const report = JSON.parse(text) as SuiteResult;
        if (!Array.isArray(report.cases)) {
          throw new Error("missing `cases` array — not a report.json");
        }
        const pass = report.cases.filter((c) => c.passed).length;
        const fail = report.cases.length - pass;
        const row: RunRow = {
          id: `local-${Date.now()}`,
          suite_hash: suiteHashOf(report),
          started_at: new Date().toISOString(),
          total_cost_usd: report.total_cost_usd ?? 0,
          pass_count: pass,
          fail_count: fail,
          raw_report: report,
        };
        onParsed(report, row);
      } catch (e) {
        setError(e instanceof Error ? e.message : "failed to parse");
      }
    },
    [onParsed],
  );

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setHover(true);
      }}
      onDragLeave={() => setHover(false)}
      onDrop={(e) => {
        e.preventDefault();
        setHover(false);
        const file = e.dataTransfer.files?.[0];
        if (file) void ingest(file);
      }}
      className={`rounded-lg border-2 border-dashed p-6 text-center transition-colors ${
        hover
          ? "border-blue-400 bg-blue-50"
          : "border-neutral-300 bg-white"
      }`}
    >
      <p className="text-sm text-neutral-600">
        Drop a <code>report.json</code> here, or
      </p>
      <label className="mt-2 inline-block cursor-pointer rounded-md bg-neutral-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-neutral-700">
        browse
        <input
          type="file"
          accept="application/json,.json"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) void ingest(file);
          }}
        />
      </label>
      {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
    </div>
  );
}
