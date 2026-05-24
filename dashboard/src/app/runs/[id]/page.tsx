"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { CaseGrid } from "@/components/CaseGrid";
import { TranscriptDrawer } from "@/components/TranscriptDrawer";
import type { RunRow, RunResult } from "@/lib/types";

export default function RunDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const [run, setRun] = useState<RunRow | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedCase, setSelectedCase] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`/api/runs/${id}`);
        if (!res.ok) throw new Error(`api/runs/${id} ${res.status}`);
        const data = (await res.json()) as { run: RunRow };
        if (!cancelled) setRun(data.run);
      } catch (e) {
        if (!cancelled)
          setError(e instanceof Error ? e.message : "failed to load");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id]);

  if (error) {
    return (
      <div className="space-y-3">
        <Link href="/" className="text-sm text-blue-600 hover:underline">
          ← back
        </Link>
        <div className="rounded border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          {error}
        </div>
      </div>
    );
  }

  if (!run) {
    return <div className="text-sm text-neutral-400">Loading…</div>;
  }

  const cases: RunResult[] = run.raw_report?.cases ?? [];
  const selected: RunResult | null = selectedCase
    ? cases.find((c) => c.case_id === selectedCase) ?? null
    : null;

  return (
    <div className="space-y-6">
      <div>
        <Link href="/" className="text-sm text-blue-600 hover:underline">
          ← back
        </Link>
        <h1 className="mt-2 text-2xl font-semibold">Run detail</h1>
        <p className="text-sm text-neutral-500">
          {new Date(run.started_at).toLocaleString()} · suite{" "}
          <code className="font-mono text-xs">{run.suite_hash}</code>
        </p>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <div className="rounded border border-neutral-200 bg-white p-4">
          <div className="text-xs uppercase text-neutral-500">Pass</div>
          <div className="text-2xl font-semibold text-green-700">
            {run.pass_count}
          </div>
        </div>
        <div className="rounded border border-neutral-200 bg-white p-4">
          <div className="text-xs uppercase text-neutral-500">Fail</div>
          <div className="text-2xl font-semibold text-red-700">
            {run.fail_count}
          </div>
        </div>
        <div className="rounded border border-neutral-200 bg-white p-4">
          <div className="text-xs uppercase text-neutral-500">Cost</div>
          <div className="text-2xl font-semibold">
            ${Number(run.total_cost_usd).toFixed(4)}
          </div>
        </div>
      </div>

      <section className="rounded-lg border border-neutral-200 bg-white p-4">
        <h2 className="mb-3 text-sm font-semibold">Cases ({cases.length})</h2>
        <CaseGrid
          cases={cases}
          selected={selectedCase}
          onSelect={setSelectedCase}
        />
      </section>

      <TranscriptDrawer
        runCase={selected}
        onClose={() => setSelectedCase(null)}
      />
    </div>
  );
}
