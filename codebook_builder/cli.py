"""codebookctl — command-line driver for the codebook generator.

Subcommands:
    codebookctl init                          - create / migrate the SQLite DB
    codebookctl ingest --qualtrics SV_xxx     - pull, normalize, store, optionally sync to Notion
    codebookctl ingest --pdf path.pdf  --survey-id SLUG
    codebookctl pull   SURVEY_ID --format xlsx [--legacy]
    codebookctl list   [--query foo]
    codebookctl runs   SURVEY_ID
    codebookctl mint-key --email someone@ucla.edu --label "Iris"
    codebookctl revoke-key --email someone@ucla.edu

All commands respect ``CODEBOOK_DB_PATH`` (default: ./codebook.sqlite).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import secrets
import sys
from pathlib import Path

from . import storage, normalize
from .normalize import PARSER_VERSION


def _add_db_arg(p: argparse.ArgumentParser) -> None:
    p.add_argument("--db", help="Path to codebook.sqlite (overrides CODEBOOK_DB_PATH)")


def cmd_init(args) -> int:
    conn = storage.connect(args.db)
    applied = storage.run_migrations(conn)
    if applied:
        print(f"[init] applied migrations: {', '.join(applied)}")
    else:
        print("[init] database already up to date.")
    print(f"[init] db path: {storage.resolve_db_path(args.db)}")
    return 0


def cmd_ingest(args) -> int:
    conn = storage.connect(args.db)
    storage.run_migrations(conn)

    if args.qualtrics:
        from .sources import qualtrics as qsrc

        survey_arg = args.qualtrics
        print(f"[ingest] resolving Qualtrics survey: {survey_arg}")
        survey_id, name, definition = qsrc.resolve_and_fetch(survey_arg)
        questions = qsrc.extract_questions(definition)
        print(f"[ingest] {len(questions)} questions extracted from {name} ({survey_id})")

        with storage.transaction(conn):
            storage.upsert_survey(
                conn,
                survey_id=survey_id,
                qualtrics_id=survey_id,
                title=name,
            )
            instrument_id = args.instrument_id or f"{survey_id}__default"
            storage.upsert_instrument(
                conn,
                instrument_id=instrument_id,
                survey_id=survey_id,
                name=name,
                role=args.role,
            )
            run_id = storage.start_run(
                conn,
                survey_id=survey_id,
                source="qualtrics",
                source_uri=survey_id,
                parser_version=PARSER_VERSION,
                claude_model=normalize.DEFAULT_MODEL if args.use_llm else None,
                triggered_by=args.triggered_by,
            )

        try:
            vars_ = normalize.normalize_qualtrics_questions(
                questions,
                use_llm=args.use_llm,
            )
            with storage.transaction(conn):
                n = storage.insert_variables(
                    conn,
                    run_id=run_id,
                    survey_id=survey_id,
                    instrument_id=instrument_id,
                    variables=vars_,
                )
                storage.finish_run(
                    conn,
                    run_id=run_id,
                    status="complete",
                    n_variables=n,
                    notes=f"{n} variables from Qualtrics {survey_id}",
                )
            print(f"[ingest] inserted {n} variables in run #{run_id}")
        except Exception as e:
            with storage.transaction(conn):
                storage.finish_run(
                    conn,
                    run_id=run_id,
                    status="failed",
                    n_variables=0,
                    notes=str(e)[:500],
                )
            raise

        if args.push_to_notion:
            _push_to_notion(run_id, conn)

        return 0

    if args.pdf or args.docx:
        from .sources import document as docsrc
        path = Path(args.pdf or args.docx)
        if not path.exists():
            print(f"[ingest] file not found: {path}", file=sys.stderr)
            return 2
        if not args.survey_id:
            print("[ingest] --survey-id is required when ingesting a document.", file=sys.stderr)
            return 2

        print(f"[ingest] extracting text from {path.name}")
        text = docsrc.extract_text(path)

        with storage.transaction(conn):
            storage.upsert_survey(
                conn,
                survey_id=args.survey_id,
                title=args.survey_title or path.stem,
            )
            instrument_id = args.instrument_id or f"{args.survey_id}__default"
            storage.upsert_instrument(
                conn,
                instrument_id=instrument_id,
                survey_id=args.survey_id,
                name=args.survey_title or path.stem,
                role=args.role,
            )
            run_id = storage.start_run(
                conn,
                survey_id=args.survey_id,
                source="pdf" if args.pdf else "docx",
                source_uri=str(path),
                parser_version=PARSER_VERSION,
                claude_model=normalize.DEFAULT_MODEL,
                triggered_by=args.triggered_by,
            )

        try:
            vars_ = normalize.normalize_document_text(text)
            with storage.transaction(conn):
                n = storage.insert_variables(
                    conn,
                    run_id=run_id,
                    survey_id=args.survey_id,
                    instrument_id=instrument_id,
                    variables=vars_,
                )
                storage.finish_run(
                    conn,
                    run_id=run_id,
                    status="complete",
                    n_variables=n,
                    notes=f"{n} variables from {path.name}",
                )
            print(f"[ingest] inserted {n} variables in run #{run_id}")
        except Exception as e:
            with storage.transaction(conn):
                storage.finish_run(
                    conn,
                    run_id=run_id,
                    status="failed",
                    n_variables=0,
                    notes=str(e)[:500],
                )
            raise

        if args.push_to_notion:
            _push_to_notion(run_id, conn)
        return 0

    print("[ingest] specify --qualtrics SV_..., --pdf file.pdf, or --docx file.docx", file=sys.stderr)
    return 2


def _push_to_notion(run_id: int, conn) -> None:
    from . import notion_sync
    print(f"[ingest] pushing run #{run_id} to Notion AWE Variables...")
    summary = notion_sync.sync_run(run_id, conn)
    print(f"[ingest] Notion sync: created={summary['created']} updated={summary['updated']}")


def cmd_pull(args) -> int:
    conn = storage.connect(args.db)
    storage.run_migrations(conn)
    rows = storage.latest_helper_rows(conn, args.survey_id, legacy=args.legacy)
    if not rows:
        print(f"[pull] no helper rows for survey {args.survey_id}", file=sys.stderr)
        return 1

    fmt = args.format
    if fmt == "json":
        print(json.dumps(rows, indent=2, default=str))
    elif fmt == "csv":
        _write_csv(sys.stdout, rows)
    elif fmt == "xlsx":
        out = Path(args.out or f"{args.survey_id}-helper.xlsx").resolve()
        _write_xlsx(out, rows)
        print(f"[pull] wrote {out}")
    return 0


def cmd_list(args) -> int:
    conn = storage.connect(args.db)
    storage.run_migrations(conn)
    rows = storage.list_surveys(conn, q=args.query)
    if not rows:
        print("[list] no surveys yet.")
        return 0
    width = max(len(r["survey_id"]) for r in rows)
    for r in rows:
        print(f"{r['survey_id']:<{width}}  {r['n_runs']:>3} run(s)  {r['title']}")
    return 0


def cmd_runs(args) -> int:
    conn = storage.connect(args.db)
    storage.run_migrations(conn)
    rows = storage.runs_for_survey(conn, args.survey_id)
    if not rows:
        print(f"[runs] no ingestion runs for {args.survey_id}")
        return 0
    for r in rows:
        print(f"#{r['id']:>4}  {r['status']:<10}  {r['n_variables']:>4} vars  "
              f"{r['source']:<12}  {r['started_at']}  {r['notes'] or ''}")
    return 0


def cmd_mint_key(args) -> int:
    conn = storage.connect(args.db)
    storage.run_migrations(conn)
    raw = secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(raw.encode()).hexdigest()
    conn.execute(
        "INSERT INTO api_keys(key_hash, user_email, label) VALUES (?,?,?)",
        (key_hash, args.email, args.label),
    )
    print("Issued new API key. Store it now — it will not be shown again:\n")
    print(f"  {raw}\n")
    print(f"User: {args.email}")
    if args.label:
        print(f"Label: {args.label}")
    return 0


def cmd_revoke_key(args) -> int:
    conn = storage.connect(args.db)
    storage.run_migrations(conn)
    cur = conn.execute(
        "UPDATE api_keys SET revoked_at = datetime('now') WHERE user_email = ? AND revoked_at IS NULL",
        (args.email,),
    )
    print(f"[revoke-key] revoked {cur.rowcount} active key(s) for {args.email}")
    return 0


def _write_csv(buf, rows: list[dict]) -> None:
    if not rows:
        return
    fields = list(rows[0].keys())
    w = csv.DictWriter(buf, fieldnames=fields)
    try:
        w.writeheader()
        for r in rows:
            w.writerow(r)
    except BrokenPipeError:
        # Consumer (e.g. `head`) closed the pipe early; that's fine.
        pass


def _write_xlsx(path: Path, rows: list[dict]) -> None:
    try:
        import openpyxl  # type: ignore
    except ImportError as e:
        raise ImportError("openpyxl is required for --format xlsx") from e

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Helper"
    if rows:
        fields = list(rows[0].keys())
        ws.append(fields)
        for r in rows:
            ws.append([r.get(f) for f in fields])
    wb.save(path)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="codebookctl", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Create / migrate the SQLite database")
    _add_db_arg(p_init)
    p_init.set_defaults(func=cmd_init)

    p_ing = sub.add_parser("ingest", help="Ingest a survey from Qualtrics or a document")
    _add_db_arg(p_ing)
    src = p_ing.add_mutually_exclusive_group()
    src.add_argument("--qualtrics", help="Qualtrics survey ID (SV_...) or title")
    src.add_argument("--pdf", help="Path to a PDF survey")
    src.add_argument("--docx", help="Path to a DOCX survey")
    p_ing.add_argument("--survey-id", help="Internal survey slug (required for PDF/DOCX)")
    p_ing.add_argument("--survey-title", help="Title to store when using --pdf/--docx")
    p_ing.add_argument("--instrument-id", help="Override the instrument id (default: <survey>__default)")
    p_ing.add_argument("--role", default="post", help="pre / post / followup / satisfaction / ...")
    p_ing.add_argument("--triggered-by", default=None, help="Email of the person initiating the run")
    p_ing.add_argument("--push-to-notion", action="store_true", help="Push the run's variables to the AWE Notion DB")
    p_ing.add_argument("--use-llm", action="store_true", default=None,
                       help="Force LLM normalization (default: auto if ANTHROPIC_API_KEY set)")
    p_ing.add_argument("--no-llm", dest="use_llm", action="store_false", help="Force rule-based fallback")
    p_ing.set_defaults(func=cmd_ingest)

    p_pull = sub.add_parser("pull", help="Export the latest helper rows for a survey")
    _add_db_arg(p_pull)
    p_pull.add_argument("survey_id")
    p_pull.add_argument("--format", choices=["csv", "json", "xlsx"], default="csv")
    p_pull.add_argument("--legacy", action="store_true", help="Use the v_helper_legacy 6-column layout")
    p_pull.add_argument("--out", help="Output path (for --format xlsx)")
    p_pull.set_defaults(func=cmd_pull)

    p_list = sub.add_parser("list", help="List known surveys")
    _add_db_arg(p_list)
    p_list.add_argument("--query", help="Filter substring")
    p_list.set_defaults(func=cmd_list)

    p_runs = sub.add_parser("runs", help="List ingestion runs for a survey")
    _add_db_arg(p_runs)
    p_runs.add_argument("survey_id")
    p_runs.set_defaults(func=cmd_runs)

    p_mint = sub.add_parser("mint-key", help="Generate a new API key")
    _add_db_arg(p_mint)
    p_mint.add_argument("--email", required=True)
    p_mint.add_argument("--label", default=None, help="Human-readable label (e.g. team member name)")
    p_mint.set_defaults(func=cmd_mint_key)

    p_rev = sub.add_parser("revoke-key", help="Revoke all active API keys for a user")
    _add_db_arg(p_rev)
    p_rev.add_argument("--email", required=True)
    p_rev.set_defaults(func=cmd_revoke_key)

    return ap


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
