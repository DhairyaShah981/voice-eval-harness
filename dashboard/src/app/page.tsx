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
          <h1 className="text-2xl font-semibold">voice-eval-harness · live demo</h1>
          <p className="text-sm text-neutral-500 max-w-3xl">
            {remoteMode
              ? "Connected to Supabase."
              : "Open-source eval harness for production voice agents — extracted from the CI gates we run on every PR at Trifetch (closed-source HIPAA agentic-clinic OS). Persona-driven adversarial simulators, LLM-as-judge with budget caps, KB-grounding checks, multi-turn memory + tool-sequence assertions, and read-only audit of real production calls. Click a demo button below to load a live run."}
          </p>
        </div>
        <a
          href="https://github.com/DhairyaShah981/voice-eval-harness"
          target="_blank"
          rel="noreferrer"
          className="rounded border border-neutral-300 bg-white px-3 py-1.5 text-xs font-medium text-neutral-700 hover:bg-neutral-100"
        >
          GitHub ↗
        </a>
      </div>

      {!remoteMode && (
        <div className="rounded-lg border border-neutral-200 bg-white p-4 text-sm">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-neutral-500 mb-2">
            What you&apos;re looking at
          </h3>
          <div className="grid sm:grid-cols-3 gap-4 text-neutral-700">
            <div>
              <div className="font-semibold text-neutral-900">Vapi GI suite</div>
              <p className="text-xs text-neutral-500 mt-1">
                6 multi-turn persona-driven cases vs a Bayview Endoscopy assistant — KB grounding, critical-phrasing, emergency triage, and a 2FA log-question flow. Cases derived from real Trifetch GI test scenarios.
              </p>
            </div>
            <div>
              <div className="font-semibold text-neutral-900">Retell prod audit</div>
              <p className="text-xs text-neutral-500 mt-1">
                <code className="text-[11px]">voxeval audit</code> read-only against 18 real production calls from a Trifetch ENT scheduling agent (last 7 days). LLM judge flags off-topic wander; clinic names anonymized.
              </p>
            </div>
            <div>
              <div className="font-semibold text-neutral-900">Click any case</div>
              <p className="text-xs text-neutral-500 mt-1">
                Transcript drawer opens with full multi-turn dialog, every assertion result (tool calls, latency, LLM-judge verdicts), and the failure narrative when the harness catches a real regression.
              </p>
            </div>
          </div>
        </div>
      )}

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
        <RunsTable rows={rows} remoteMode={remoteMode} />
      )}

      <TranscriptDrawer
        runCase={selected}
        onClose={() => setSelectedCase(null)}
      />
    </div>
  );
}
