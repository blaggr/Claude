"""Survey codebook generator for the AVA Lab.

Public entry points:
    codebook_builder.storage  — SQLite schema + connection helpers
    codebook_builder.sources  — Qualtrics / document / link ingestors
    codebook_builder.normalize — Claude-based question normalizer
    codebook_builder.notion_sync — push canonical metadata back to Notion
    codebook_builder.cli      — `codebookctl` entry point
"""
__version__ = "0.1.0"
