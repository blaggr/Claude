"""Pydantic models for the codebook FastAPI service."""
from __future__ import annotations

from pydantic import BaseModel, Field


class IngestRequest(BaseModel):
    source: str = Field(..., description="qualtrics | pdf | docx | url")
    survey_id: str | None = Field(None, description="Internal slug (required for pdf/docx/url)")
    survey_title: str | None = None
    qualtrics_arg: str | None = Field(None, description="Survey ID (SV_...) or title substring")
    url: str | None = None
    instrument_id: str | None = None
    role: str | None = "post"
    push_to_notion: bool = False


class IngestResponse(BaseModel):
    run_id: int
    survey_id: str
    status: str


class RunSummary(BaseModel):
    id: int
    survey_id: str
    source: str
    source_uri: str | None
    started_at: str
    finished_at: str | None
    status: str
    n_variables: int
    notes: str | None


class SurveySummary(BaseModel):
    survey_id: str
    qualtrics_id: str | None
    title: str
    owner: str | None
    n_runs: int
    last_seen_at: str


class HelperRow(BaseModel):
    model_config = {"extra": "allow"}
