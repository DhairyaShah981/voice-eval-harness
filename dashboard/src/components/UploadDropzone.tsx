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

  const ingestReport = useCallback(
    (report: SuiteResult, sourceLabel: string) => {
      if (!Array.isArray(report.cases)) {
        throw new Error("missing `cases` array — not a report.json");
      }
      const pass = report.cases.filter((c) => c.passed).length;
      const fail = report.cases.length - pass;
      const row: RunRow = {
        id: `${sourceLabel}-${Date.now()}`,
        suite_hash: suiteHashOf(report),
        started_at: new Date().toISOString(),
        total_cost_usd: report.total_cost_usd ?? 0,
        pass_count: pass,
        fail_count: fail,
        raw_report: report,
      };
      onParsed(report, row);
    },
    [onParsed],
  );

  const ingest = useCallback(
    async (file: File) => {
      setError(null);
      try {
        const text = await file.text();
        const report = JSON.parse(text) as SuiteResult;
        ingestReport(report, "local");
      } catch (e) {
        setError(e instanceof Error ? e.message : "failed to parse");
      }
    },
    [ingestReport],
  );

  const loadSampleFrom = useCallback(
    async (url: string, label: string) => {
      setError(null);
      try {
        const res = await fetch(url, { cache: "no-store" });
        if (!res.ok) throw new Error(`sample fetch failed: ${res.status}`);
        const report = (await res.json()) as SuiteResult;
        ingestReport(report, label);
      } catch (e) {
        setError(e instanceof Error ? e.message : "failed to load sample");
      }
    },
    [ingestReport],
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
      <div className="mt-2 flex items-center justify-center gap-2">
        <label className="inline-block cursor-pointer rounded-md bg-neutral-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-neutral-700">
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
        <button
          type="button"
          onClick={() => void loadSampleFrom("/sample-report-vapi.json", "vapi-demo")}
          className="inline-block cursor-pointer rounded-md border border-neutral-300 bg-white px-3 py-1.5 text-xs font-medium text-neutral-900 hover:bg-neutral-100"
        >
          Vapi live demo ▶
        </button>
        <button
          type="button"
          onClick={() => void loadSampleFrom("/sample-report-retell.json", "retell-audit")}
          className="inline-block cursor-pointer rounded-md border border-neutral-300 bg-white px-3 py-1.5 text-xs font-medium text-neutral-900 hover:bg-neutral-100"
        >
          Retell prod audit ▶
        </button>
      </div>
      <p className="mt-2 text-[11px] text-neutral-400">
        Vapi GI suite: 6 multi-turn persona-driven cases vs a Bayview Endoscopy assistant — KB grounding, critical-phrasing, emergency triage, 2FA log-question flow.<br />
        Retell prod audit: <code>voxeval audit</code> read-only against 18 real production calls from a Trifetch ENT scheduling agent (last 7 days, clinic names anonymised).
      </p>
      {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
    </div>
  );
}
