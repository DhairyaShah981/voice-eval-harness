#!/usr/bin/env bash
# Apply the dashboard's Supabase schema to your project.
#
# Two paths:
#
# 1. AUTOMATED — requires either a Supabase PAT (personal access token) or
#    the `supabase` CLI logged into your account:
#
#       brew install supabase/tap/supabase  # one-time
#       supabase login                       # opens browser
#       supabase link --project-ref eneicikowlcpgcvawake
#       supabase db push                     # applies schema.sql from supabase/
#
#    (You'll need to copy dashboard/supabase/schema.sql to supabase/migrations/
#    or run it directly via `supabase db query --file dashboard/supabase/schema.sql`.)
#
# 2. CLICK-THROUGH — open the SQL editor and paste:
#
#       https://supabase.com/dashboard/project/eneicikowlcpgcvawake/sql/new
#
#    Paste dashboard/supabase/schema.sql contents, click "Run".
#
# Either way, after the schema is live, paste your SECRET key into
# dashboard/.env.local:
#
#       SUPABASE_SECRET_KEY=sb_secret_...      (or service_role JWT)
#
# Find it at:
#       https://supabase.com/dashboard/project/eneicikowlcpgcvawake/settings/api

set -e

PROJECT_REF="eneicikowlcpgcvawake"
SCHEMA_FILE="dashboard/supabase/schema.sql"

if [ ! -f "$SCHEMA_FILE" ]; then
  echo "ERROR: $SCHEMA_FILE not found. Run from voice-eval-harness repo root."
  exit 1
fi

echo ""
echo "=== Supabase schema for project '$PROJECT_REF' ==="
echo ""
echo "File: $SCHEMA_FILE ($(wc -l < $SCHEMA_FILE) lines)"
echo ""
echo "To apply via the SQL editor (recommended for first-time setup):"
echo ""
echo "  1. Open: https://supabase.com/dashboard/project/$PROJECT_REF/sql/new"
echo "  2. Paste the contents of $SCHEMA_FILE"
echo "  3. Click 'Run'"
echo ""
echo "After the schema is applied, add the secret key to dashboard/.env.local:"
echo ""
echo "  SUPABASE_SECRET_KEY=sb_secret_..."
echo ""
echo "Find it at:"
echo "  https://supabase.com/dashboard/project/$PROJECT_REF/settings/api"
echo ""
echo "Then start the dashboard:"
echo ""
echo "  cd dashboard && pnpm dev"
echo ""
