"""API-key authentication for the codebook FastAPI service.

Keys are minted via ``codebookctl mint-key``. We store only the SHA-256 hash;
clients pass the raw key in the ``X-API-Key`` header (or an ``Authorization:
Bearer <key>`` header — equivalent).
"""
from __future__ import annotations

import hashlib

from fastapi import Header, HTTPException, status

from codebook_builder import storage


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def verify_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
) -> dict:
    """FastAPI dependency. Returns the authenticated api_keys row.

    Disabled (returns a sentinel) when CODEBOOK_DISABLE_AUTH=1 — local dev only.
    """
    import os
    if os.environ.get("CODEBOOK_DISABLE_AUTH") == "1":
        return {"user_email": "dev@localhost", "label": "auth-disabled"}

    raw = x_api_key
    if not raw and authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer":
            raw = token

    if not raw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Provide X-API-Key (or Authorization: Bearer <key>) header.",
        )

    conn = storage.connect()
    storage.run_migrations(conn)
    row = conn.execute(
        "SELECT * FROM api_keys WHERE key_hash = ? AND revoked_at IS NULL",
        (_hash(raw),),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid or revoked API key.")
    conn.execute(
        "UPDATE api_keys SET last_used_at = datetime('now') WHERE key_hash = ?",
        (_hash(raw),),
    )
    return dict(row)
