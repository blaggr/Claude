# Helper file schema — "Internal Helper Columns"

The AVA Lab codebook generator stores survey metadata in SQLite using a
normalized schema (Variable + ResponseOption) and exposes it for Alteryx via
two views:

## `v_helper_modern` (preferred)

One row per (variable × response option). Use this in new Alteryx workflows.

| Column            | Type    | Source                              | Notes |
|-------------------|---------|-------------------------------------|-------|
| `SurveyID`        | TEXT    | surveys.survey_id                   | Internal slug (or `SV_…` when ingested via Qualtrics) |
| `QualtricsID`     | TEXT    | surveys.qualtrics_id                | `SV_…` if available |
| `SurveyTitle`     | TEXT    | surveys.title                       | |
| `InstrumentID`    | TEXT    | instruments.instrument_id           | Canonical short id |
| `InstrumentName`  | TEXT    | instruments.name                    | |
| `InstrumentRole`  | TEXT    | instruments.role                    | pre / post / followup / satisfaction / … |
| `VariableName`    | TEXT    | variables.variable_name             | Snake-case canonical id |
| `QuestionText`    | TEXT    | variables.question_text             | Prompt only |
| `Label`           | TEXT    | variables.label                     | Full item text (with sub-question for matrix rows) |
| `VariableType`    | TEXT    | variables.variable_type             | Likert / Multiple Choice / Free Text / Numeric / Date / Composite / Derived / Demographic / Unknown |
| `Domain`          | TEXT    | variables.domain                    | Comma-separated. From AWE Variables schema. |
| `Dimension`       | TEXT    | variables.dimension                 | Finer sub-grouping |
| `Scale`           | TEXT    | variables.scale                     | Short description of the response scale |
| `ReverseScored`   | INTEGER | variables.reverse_scored            | 0 / 1 |
| `DerivationLogic` | TEXT    | variables.derivation_logic          | For composites |
| `SourceInstrument`| TEXT    | variables.source_instrument         | |
| `COURS`           | TEXT    | variables.cours                     | AVAL training-code (e.g. `P11_DT_OV_CO_SD_Survey123`) |
| `Flag`            | TEXT    | variables.flag                      | "Needs Rob Review" \| "Confirmed" \| NULL |
| `Position`        | INTEGER | variables.position                  | Ordering within the instrument |
| `Value_Numeric`   | REAL    | response_options.value_numeric      | Numeric label (NULL for free-text/derived) |
| `Value_Text`      | TEXT    | response_options.value_text         | Display label |
| `Value_Order`     | INTEGER | response_options.order_index        | Original scale ordering |
| `IngestionRunID`  | INTEGER | variables.ingestion_run_id          | Which run produced this row |
| `IngestedAt`      | TEXT    | ingestion_runs.started_at           | ISO 8601 |

The view filters to MAX(ingestion_run_id) per survey, so it always returns the
latest version. To see an older version, query the underlying tables directly
with the `IngestionRunID` you want.

## `v_helper_legacy` (6-column, back-compat)

Matches the columns the existing "Helper Dictionary Label Workflow.yxzp" reads.

| Column          | Mapping                                |
|-----------------|----------------------------------------|
| `Class`         | `variables.cours`                      |
| `Timestamp`     | always NULL (data file holds timestamps, not the codebook) |
| `Dimension`     | `variables.dimension`                  |
| `Name`          | `COALESCE(variables.label, variables.question_text)` |
| `Value_Numeric` | `response_options.value_numeric`       |
| `Value_Text`    | `response_options.value_text`          |

Both views default to the latest run for each survey.

## Versioning

Every ingest creates a new row in `ingestion_runs`. The variables and response
options for that run are linked via `variables.ingestion_run_id`. Old runs are
never deleted; both views filter to the latest `status='complete'` run per
survey. To roll back, mark the broken run `cancelled` — the previous complete
run becomes "latest" again automatically.
