import { NextRequest, NextResponse } from "next/server";
import { getSupabaseAdmin, supabaseConfigured } from "@/lib/supabase";
import type { RunRow, SuiteResult } from "@/lib/types";

export const dynamic = "force-dynamic";

// Stable suite hash from case IDs only (no crypto dep — good enough for v0.2).
function suiteHash(report: SuiteResult): string {
  const s = report.cases.map((c) => c.case_id).join("|");
  let h = 0;
  for (let i = 0; i < s.length; i++) {
    h = (h << 5) - h + s.charCodeAt(i);
    h |= 0;
  }
  return Math.abs(h).toString(16).padStart(8, "0");
}

export async function GET(): Promise<NextResponse> {
  const sb = getSupabaseAdmin();
  if (!sb) {
    return NextResponse.json({ rows: [] as RunRow[], remote: false });
  }
  const { data, error } = await sb
    .from("runs")
    .select(
      "id, suite_hash, started_at, total_cost_usd, pass_count, fail_count",
    )
    .order("started_at", { ascending: false })
    .limit(100);
  if (error) {
    return NextResponse.json(
      { error: error.message, rows: [] as RunRow[], remote: true },
      { status: 500 },
    );
  }
  return NextResponse.json({ rows: data ?? [], remote: true });
}

export async function POST(req: NextRequest): Promise<NextResponse> {
  const auth = req.headers.get("authorization") ?? "";
  const expected = process.env.RUNS_INGEST_TOKEN;
  if (!expected || auth !== `Bearer ${expected}`) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  let report: SuiteResult;
  try {
    report = (await req.json()) as SuiteResult;
  } catch {
    return NextResponse.json({ error: "invalid json" }, { status: 400 });
  }
  if (!report || !Array.isArray(report.cases)) {
    return NextResponse.json(
      { error: "missing `cases` array" },
      { status: 400 },
    );
  }

  if (!supabaseConfigured) {
    return NextResponse.json(
      { error: "supabase not configured on server" },
      { status: 503 },
    );
  }

  const sb = getSupabaseAdmin();
  if (!sb) {
    return NextResponse.json(
      { error: "service role key missing" },
      { status: 503 },
    );
  }

  // Workspace ID resolution is stubbed — production would derive from the
  // ingest token. For now we accept it as a header or fall back to a fixed UUID.
  const workspaceId =
    req.headers.get("x-workspace-id") ?? "00000000-0000-0000-0000-000000000000";

  const pass = report.cases.filter((c) => c.passed).length;
  const fail = report.cases.length - pass;

  const { data: run, error: runErr } = await sb
    .from("runs")
    .insert({
      suite_hash: suiteHash(report),
      workspace_id: workspaceId,
      total_cost_usd: report.total_cost_usd ?? 0,
      pass_count: pass,
      fail_count: fail,
      raw_report: report,
    })
    .select("id")
    .single();

  if (runErr || !run) {
    return NextResponse.json(
      { error: runErr?.message ?? "insert failed" },
      { status: 500 },
    );
  }

  const caseRows = report.cases.map((c) => ({
    run_id: run.id,
    case_id: c.case_id,
    passed: c.passed,
    duration_ms: c.duration_ms,
    cost_usd: c.cost_usd ?? 0,
    error: c.error,
  }));
  if (caseRows.length) {
    const { data: inserted, error: caseErr } = await sb
      .from("cases")
      .insert(caseRows)
      .select("id, case_id");
    if (caseErr) {
      return NextResponse.json({ error: caseErr.message }, { status: 500 });
    }

    const idByCaseId = new Map(inserted?.map((c) => [c.case_id, c.id]) ?? []);
    const assertionRows = report.cases.flatMap((c) =>
      c.assertion_results.map((a) => ({
        case_id_fk: idByCaseId.get(c.case_id),
        kind: a.kind,
        passed: a.passed,
        detail: a.detail,
      })),
    );
    if (assertionRows.length) {
      const { error: aErr } = await sb.from("assertions").insert(assertionRows);
      if (aErr) {
        return NextResponse.json({ error: aErr.message }, { status: 500 });
      }
    }
  }

  return NextResponse.json({ id: run.id }, { status: 201 });
}
