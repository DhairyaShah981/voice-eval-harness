"use client";

import Link from "next/link";
import { PassRateSparkline } from "./PassRateSparkline";
import type { RunRow } from "@/lib/types";

interface Props {
  rows: RunRow[];
  remoteMode?: boolean;
}

function isLocalRow(id: string): boolean {
  // Local-mode rows are not persisted to Supabase; their detail page would
  // 404 on /api/runs/[id]. Render as plain text instead of a link.
  return (
    id.startsWith("local-") ||
    id.startsWith("demo-") ||
    id.startsWith("vapi-demo-") ||
    id.startsWith("retell-audit-")
  );
}

export function RunsTable({ rows, remoteMode = false }: Props) {
  if (!rows.length) {
    return (
      <div className="rounded-lg border border-dashed border-neutral-300 p-8 text-center text-sm text-neutral-500">
        {remoteMode
          ? <>No runs persisted yet. Upload a <code>report.json</code> above or POST one to <code>/api/runs</code>.</>
          : <>This dashboard is in <strong>local mode</strong> &mdash; in-memory only. Click <strong>Vapi live demo</strong> or <strong>Retell prod audit</strong> above to load a real eval.</>
        }
      </div>
    );
  }

  // Build a sparkline from cumulative recent runs (oldest -> newest of the visible window).
  const recent = [...rows].slice(0, 10).reverse();
  const sparkValues = recent.map((r) => {
    const total = r.pass_count + r.fail_count;
    return total === 0 ? 0 : r.pass_count / total;
  });

  return (
    <div className="overflow-hidden rounded-lg border border-neutral-200 bg-white">
      <table className="w-full text-sm">
        <thead className="bg-neutral-50 text-left text-xs uppercase tracking-wide text-neutral-500">
          <tr>
            <th className="px-4 py-2">When</th>
            <th className="px-4 py-2">Suite hash</th>
            <th className="px-4 py-2">Pass rate</th>
            <th className="px-4 py-2">Trend</th>
            <th className="px-4 py-2 text-right">Cost</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-neutral-100">
          {rows.map((r) => {
            const total = r.pass_count + r.fail_count;
            const rate = total === 0 ? 0 : r.pass_count / total;
            return (
              <tr key={r.id} className="hover:bg-neutral-50">
                <td className="px-4 py-3">
                  {isLocalRow(r.id) ? (
                    <span className="text-neutral-700">
                      {new Date(r.started_at).toLocaleString()}
                      <span className="ml-2 inline-block rounded bg-neutral-100 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-neutral-500">
                        local
                      </span>
                    </span>
                  ) : (
                    <Link
                      href={`/runs/${r.id}`}
                      className="text-blue-600 hover:underline"
                    >
                      {new Date(r.started_at).toLocaleString()}
                    </Link>
                  )}
                </td>
                <td className="px-4 py-3 font-mono text-xs text-neutral-600">
                  {r.suite_hash.slice(0, 12)}
                </td>
                <td className="px-4 py-3">
                  <span
                    className={
                      rate >= 0.9
                        ? "text-green-700"
                        : rate >= 0.7
                          ? "text-yellow-700"
                          : "text-red-700"
                    }
                  >
                    {(rate * 100).toFixed(0)}%
                  </span>{" "}
                  <span className="text-xs text-neutral-400">
                    ({r.pass_count}/{total})
                  </span>
                </td>
                <td className="px-4 py-3">
                  <PassRateSparkline values={sparkValues} />
                </td>
                <td className="px-4 py-3 text-right font-mono">
                  ${Number(r.total_cost_usd).toFixed(4)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
