-- 0002_views.sql
-- Alteryx-facing views. Drop+recreate is safe in SQLite for views.

DROP VIEW IF EXISTS v_latest_run;
CREATE VIEW v_latest_run AS
SELECT survey_id, MAX(id) AS ingestion_run_id
FROM   ingestion_runs
WHERE  status = 'complete'
GROUP  BY survey_id;

-- Modern "Internal Helper Columns" layout: one row per variable × response option,
-- with all the metadata Alteryx workflows need.
DROP VIEW IF EXISTS v_helper_modern;
CREATE VIEW v_helper_modern AS
SELECT
    s.survey_id                          AS SurveyID,
    s.qualtrics_id                       AS QualtricsID,
    s.title                              AS SurveyTitle,
    i.instrument_id                      AS InstrumentID,
    i.name                               AS InstrumentName,
    i.role                               AS InstrumentRole,
    v.variable_name                      AS VariableName,
    v.question_text                      AS QuestionText,
    v.label                              AS Label,
    v.variable_type                      AS VariableType,
    v.domain                             AS Domain,
    v.dimension                          AS Dimension,
    v.scale                              AS Scale,
    v.reverse_scored                     AS ReverseScored,
    v.derivation_logic                   AS DerivationLogic,
    v.source_instrument                  AS SourceInstrument,
    v.cours                              AS COURS,
    v.flag                               AS Flag,
    v.position                           AS Position,
    ro.value_numeric                     AS Value_Numeric,
    ro.value_text                        AS Value_Text,
    ro.order_index                       AS Value_Order,
    v.ingestion_run_id                   AS IngestionRunID,
    r.started_at                         AS IngestedAt
FROM       variables       v
JOIN       v_latest_run    lr ON lr.ingestion_run_id = v.ingestion_run_id
JOIN       surveys         s  ON s.survey_id        = v.survey_id
LEFT JOIN  instruments     i  ON i.instrument_id    = v.instrument_id
LEFT JOIN  response_options ro ON ro.variable_id    = v.variable_id
JOIN       ingestion_runs  r  ON r.id               = v.ingestion_run_id;

-- Legacy 6-column layout that today's Helper Dictionary Label Workflow consumes.
-- Class is the AVAL training "Class" code; we map it from COURS for now.
DROP VIEW IF EXISTS v_helper_legacy;
CREATE VIEW v_helper_legacy AS
SELECT
    v.cours                              AS Class,
    NULL                                 AS Timestamp,    -- responses live elsewhere
    v.dimension                          AS Dimension,
    COALESCE(v.label, v.question_text)   AS Name,
    ro.value_numeric                     AS Value_Numeric,
    ro.value_text                        AS Value_Text
FROM       variables       v
JOIN       v_latest_run    lr ON lr.ingestion_run_id = v.ingestion_run_id
LEFT JOIN  response_options ro ON ro.variable_id    = v.variable_id;

INSERT OR IGNORE INTO schema_migrations(version) VALUES ('0002_views');
