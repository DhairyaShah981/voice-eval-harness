import { NextResponse } from "next/server";
import { getSupabaseAdmin } from "@/lib/supabase";

export const dynamic = "force-dynamic";

export async function GET(
  _req: Request,
  ctx: { params: Promise<{ id: string }> },
): Promise<NextResponse> {
  const { id } = await ctx.params;
  const sb = getSupabaseAdmin();
  if (!sb) {
    return NextResponse.json(
      { error: "supabase not configured" },
      { status: 503 },
    );
  }
  const { data, error } = await sb
    .from("runs")
    .select(
      "id, suite_hash, started_at, total_cost_usd, pass_count, fail_count, raw_report",
    )
    .eq("id", id)
    .single();
  if (error || !data) {
    return NextResponse.json(
      { error: error?.message ?? "not found" },
      { status: 404 },
    );
  }
  return NextResponse.json({ run: data });
}
