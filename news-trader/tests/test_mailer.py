"""Unit tests for mailer.py — all offline, no real SMTP."""
from __future__ import annotations
import os
import pytest
from mailer import MailError, mail_config, build_message, send_email


# ---------------------------------------------------------------------------
# mail_config
# ---------------------------------------------------------------------------

def test_mail_config_raises_when_smtp_user_missing(monkeypatch):
    monkeypatch.delenv("SMTP_USER", raising=False)
    monkeypatch.setenv("SMTP_PASS", "app_password")
    monkeypatch.setenv("MAIL_TO", "dest@example.com")
    with pytest.raises(MailError, match="SMTP_USER"):
        mail_config()


def test_mail_config_raises_when_smtp_pass_missing(monkeypatch):
    monkeypatch.setenv("SMTP_USER", "user@example.com")
    monkeypatch.delenv("SMTP_PASS", raising=False)
    monkeypatch.setenv("MAIL_TO", "dest@example.com")
    with pytest.raises(MailError, match="SMTP_PASS"):
        mail_config()


def test_mail_config_raises_when_mail_to_missing(monkeypatch):
    monkeypatch.setenv("SMTP_USER", "user@example.com")
    monkeypatch.setenv("SMTP_PASS", "app_password")
    monkeypatch.delenv("MAIL_TO", raising=False)
    with pytest.raises(MailError, match="MAIL_TO"):
        mail_config()


def test_mail_config_defaults(monkeypatch):
    monkeypatch.setenv("SMTP_USER", "user@example.com")
    monkeypatch.setenv("SMTP_PASS", "secret")
    monkeypatch.setenv("MAIL_TO", "dest@example.com")
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("SMTP_PORT", raising=False)
    monkeypatch.delenv("MAIL_FROM", raising=False)
    cfg = mail_config()
    assert cfg["host"] == "smtp.gmail.com"
    assert cfg["port"] == 587
    assert cfg["from"] == "user@example.com"   # falls back to SMTP_USER


# ---------------------------------------------------------------------------
# build_message
# ---------------------------------------------------------------------------

_CFG = {"host": "smtp.gmail.com", "port": 587, "user": "u@example.com",
        "password": "pw", "from": "sender@example.com", "to": "recv@example.com"}


def test_build_message_headers():
    msg = build_message("Test subject", "Hello body", _CFG)
    assert msg["Subject"] == "Test subject"
    assert msg["From"] == "sender@example.com"
    assert msg["To"] == "recv@example.com"


def test_build_message_body():
    msg = build_message("S", "my body text", _CFG)
    assert "my body text" in msg.get_content()


# ---------------------------------------------------------------------------
# send_email with injected transport
# ---------------------------------------------------------------------------

def test_send_email_calls_transport_once():
    calls = []

    def fake_transport(msg, cfg):
        calls.append((msg, cfg))

    send_email("Hello", "World", cfg=_CFG, transport=fake_transport)

    assert len(calls) == 1
    sent_msg, sent_cfg = calls[0]
    assert sent_msg["Subject"] == "Hello"
    assert sent_msg["From"] == _CFG["from"]
    assert sent_msg["To"] == _CFG["to"]
    assert "World" in sent_msg.get_content()
    assert sent_cfg is _CFG


def test_send_email_message_fields_via_transport():
    received = {}

    def capture(msg, cfg):
        received["subject"] = msg["Subject"]
        received["body"] = msg.get_content()

    send_email("My Subject", "My Body", cfg=_CFG, transport=capture)
    assert received["subject"] == "My Subject"
    assert "My Body" in received["body"]
