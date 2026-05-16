# API reference — AVA Lab Codebook API

Base URL: `http://<host>:8787`
Auth: send `X-API-Key: <your key>` (or `Authorization: Bearer <your key>`).
Disable for local dev with `CODEBOOK_DISABLE_AUTH=1`.

## `GET /health`

Public. Returns counts.

```json
{"status": "ok", "surveys": 12, "variables": 1408}
```

## `POST /ingest`

`multipart/form-data` so PDF / DOCX uploads work.

| Field             | Required when source = |
|-------------------|------------------------|
| `source`          | always (`qualtrics` \| `pdf` \| `docx` \| `url`) |
| `qualtrics_arg`   | `qualtrics`            |
| `survey_id`       | `pdf`, `docx`          |
| `survey_title`    | optional               |
| `instrument_id`   | optional               |
| `role`            | optional (default `post`) |
| `push_to_notion`  | optional bool          |
| `file`            | `pdf`, `docx`          |

Returns:

```json
{"run_id": 17, "survey_id": "SV_abc", "status": "complete"}
```

## `GET /runs/{run_id}`

Run metadata.

## `GET /helper?survey_id=...&format=csv|json`

Latest "Internal Helper Columns" rows for the survey.
Use `/helper/legacy` for the 6-column layout.

## `GET /variables?survey_id=...&domain=...&variable_type=...`

JSON-only filtered variables. Useful for Alteryx Download → JSON Parse paths
where you want to slice by domain (e.g. all `Self-Efficacy` items).

## `GET /surveys?q=...`

Typeahead by id / title.

## Examples

```bash
# kick off a Qualtrics ingest
curl -X POST http://localhost:8787/ingest \
     -H "X-API-Key: $KEY" \
     -F source=qualtrics -F qualtrics_arg=SV_abc123 -F role=post

# pull the modern helper as CSV
curl "http://localhost:8787/helper?survey_id=SV_abc123&format=csv" \
     -H "X-API-Key: $KEY" -o helper.csv

# legacy 6-column layout
curl "http://localhost:8787/helper/legacy?survey_id=SV_abc123&format=csv" \
     -H "X-API-Key: $KEY" -o helper_legacy.csv
```
