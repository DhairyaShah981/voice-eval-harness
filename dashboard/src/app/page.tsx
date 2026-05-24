"use client";

import { useEffect, useState } from "react";
import { RunsTable } from "@/components/RunsTable";
import { UploadDropzone } from "@/components/UploadDropzone";
import { CaseGrid } from "@/components/CaseGrid";
import { TranscriptDrawer } from "@/components/TranscriptDrawer";
import type { RunRow, RunResult, SuiteResult } from "@/lib/types";

export default function HomePage() {
  const [rows, setRows] = useState<RunRow[]>([]);
  const [localReport, setLocalReport] = useState<SuiteResult | null>(null);
  const [selectedCase, setSelectedCase] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [remoteMode, setRemoteMode] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/runs");
        if (!res.ok) throw new Error(`api/runs ${res.status}`);
        const data = (await res.json()) as { rows: RunRow[]; remote: boolean };
        if (!cancelled) {
          setRows(data.rows);
          setRemoteMode(data.remote);
        }
      } catch {
        // local mode — leave rows empty
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleParsed = (report: SuiteResult, row: RunRow) => {
    setLocalReport(report);
    setRows((prev) => [row, ...prev]);
  };

  const selected: RunResult | null =
    localReport && selectedCase
      ? localReport.cases.find((c) => c.case_id === selectedCase) ?? null
      : null;

  return (
    <div className="space-y-6">
      <div className="flex items-baseline justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Runs</h1>
          <p className="text-sm text-neutral-500">
            {remoteMode
              ? "Connected to Supabase."
              : "Local mode — uploads stay in this browser tab."}
          </p>
        </div>
        <select
          disabled
          className="rounded border border-neutral-300 bg-neutral-50 px-2 py-1 text-xs text-neutral-400"
          title="Diff view ships in v0.2.1"
        >
          <option>Diff with… (coming soon)</option>
        </select>
      </div>

      <UploadDropzone onParsed={handleParsed} />

      {localReport && (
        <section className="rounded-lg border border-neutral-200 bg-white p-4">
          <h2 className="mb-3 text-sm font-semibold">
            Just-uploaded report ({localReport.cases.length} cases)
          </h2>
          <CaseGrid
            cases={localReport.cases}
            selected={selectedCase}
            onSelect={setSelectedCase}
          />
        </section>
      )}

      {loading ? (
        <div className="text-sm text-neutral-400">Loading…</div>
      ) : (
        <RunsTable rows={rows} />
      )}

      <TranscriptDrawer
        runCase={selected}
        onClose={() => setSelectedCase(null)}
      />
    </div>
  );
}
