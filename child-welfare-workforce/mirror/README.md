# Mirrors

The repo (`data/*.csv` → `db/cww.db`) is the source of truth. These mirror a
human-friendly view out for browsing/sharing.

## Notion (live)
- **Database:** Child Welfare Workforce — Agencies
- **URL:** https://app.notion.com/p/d83fb61e81ca49feaece663884ab54ca
- **Data source ID:** `fc25ce7e-6c92-4178-9eb8-60f3b3a83287`
- One page per state agency with the core metrics (latest value) + admin
  structure. Created and populated via the Notion MCP connection.
- **Refresh:** the weekly agent re-syncs via the Notion MCP tools (preferred in
  an interactive/Action Claude session). Alternatively, `to_notion.py` upserts
  via the public REST API — set `NOTION_API_KEY` and
  `NOTION_DATABASE_ID=fc25ce7e-6c92-4178-9eb8-60f3b3a83287`.
- The Notion view is a summary; full provenance, every observation, and
  confidence tiers live in the repo.

## Google Sheets (optional, not yet configured)
`to_sheets.py` pushes the flattened latest-value view. Set `CWW_SHEET_ID` and
`GOOGLE_APPLICATION_CREDENTIALS`. Runs as a no-op dry run until configured.
