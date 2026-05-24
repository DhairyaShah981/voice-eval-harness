import { createClient, SupabaseClient } from "@supabase/supabase-js";

// Supports BOTH key naming conventions:
//   - Legacy: NEXT_PUBLIC_SUPABASE_ANON_KEY  (JWT anon key)
//   - 2026+:  NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY  (sb_publishable_...)
const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
const browserKey =
  process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ||
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

// Server-side admin key: sb_secret_... (new) or service_role JWT (legacy).
const serverKey =
  process.env.SUPABASE_SECRET_KEY || process.env.SUPABASE_SERVICE_ROLE_KEY;

export const supabaseConfigured = Boolean(url && browserKey);

/** Browser/SSR client — uses the publishable/anon key. Returns null if env vars are unset. */
export function getSupabase(): SupabaseClient | null {
  if (!url || !browserKey) return null;
  return createClient(url, browserKey, {
    auth: { persistSession: false },
  });
}

/** Server-only client with the secret/service-role key. Bypasses RLS. */
export function getSupabaseAdmin(): SupabaseClient | null {
  if (!url || !serverKey) return null;
  return createClient(url, serverKey, {
    auth: { persistSession: false },
  });
}
