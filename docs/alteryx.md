# Pulling helper files into Alteryx

Three patterns, pick whichever fits the workflow:

## 1. Direct ODBC (recommended for batch / scheduled workflows)

Reads straight from the SQLite file on Box.

1. Install the [SQLite ODBC driver](http://www.ch-werner.de/sqliteodbc/) on the
   workstation Alteryx Desktop runs on.
2. Create a User DSN named `AVAL_CODEBOOK` pointing at
   `~/Library/CloudStorage/Box-Box/UCCF_Flash/AWE_Database/codebook.sqlite`
   (or wherever the API server writes it).
3. In Alteryx: **Input Data → ODBC → AVAL_CODEBOOK → v_helper_modern**.
4. Filter by `SurveyID = "SV_xxx"` or join to your survey-ID list table.

Notes:
- Open the DSN as **read-only** — the API server is the only writer.
- The view always returns the latest ingestion run for each survey. Use the
  underlying tables directly if you need an older version (filter on
  `IngestionRunID`).

## 2. REST API via Download tool (for ad-hoc pulls)

```text
Download tool →
  URL:    http://<api-host>:8787/helper?survey_id=SV_xxx&format=csv
  Header: X-API-Key: <your key>
```

The response is a CSV ready to feed into a Text Input or Parse tool. Replace
`/helper` with `/helper/legacy` if you need the 6-column layout that the
existing "Helper Dictionary Label Workflow.yxzp" expects.

To generate an API key for a teammate, run::

    codebookctl mint-key --email someone@ucla.edu --label "Iris"

The raw key is printed once; store it in 1Password and share via your normal
secrets channel.

## 3. Run command tool (for self-contained workflows)

If the workstation has the codebook_builder package installed::

    codebookctl pull SV_xxx --format xlsx --out helper.xlsx

The `Run Command` tool fires this, then a downstream Input Data reads
`helper.xlsx`. Handy for workflows you want to ship to a teammate without
asking them to wire up ODBC.

## Refreshing a survey

When a survey changes in Qualtrics, run::

    codebookctl ingest --qualtrics SV_xxx --push-to-notion

That creates a new `ingestion_run`, and `v_helper_modern` immediately reflects
it. Old versions remain queryable.
