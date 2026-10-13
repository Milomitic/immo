"""Saved-search e-mail digest, with a fake SMTP server."""

import json
import smtplib

import pytest

from app.config import settings
from app.models.alert import SearchAlert
from app.services import alert_service
from app.services.alert_service import send_alert_digest
from tests.conftest import make_listing


class FakeSMTP:
    sent: list = []

    def __init__(self, host, port, timeout=None):
        self.host = host

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        pass

    def login(self, user, password):
        pass

    def send_message(self, msg):
        FakeSMTP.sent.append(msg)


@pytest.fixture
def smtp(monkeypatch):
    FakeSMTP.sent = []
    monkeypatch.setattr(alert_service.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.test")
    monkeypatch.setattr(settings, "ALERT_EMAIL_TO", "me@example.test")
    return FakeSMTP


@pytest.fixture
async def alert(db_session):
    row = SearchAlert(name="Bari", filters=json.dumps({"city": "bari"}),
                      created_at="2026-06-01T00:00:00+00:00")
    db_session.add_all([
        row,
        make_listing(source_id="n", title="Trilocale nuovo", first_seen_at="2026-09-01T00:00:00+00:00"),
        make_listing(source_id="o", title="Vecchio annuncio", first_seen_at="2026-01-01T00:00:00+00:00"),
    ])
    await db_session.commit()
    return row


def _plain(msg) -> str:
    return msg.get_body(("plain",)).get_content()


async def test_nothing_is_sent_without_smtp(alert, monkeypatch):
    monkeypatch.setattr(settings, "SMTP_HOST", "")
    assert await send_alert_digest() == 0


async def test_digest_lists_new_matches_once(alert, smtp):
    assert await send_alert_digest() == 1
    body = _plain(smtp.sent[0])
    assert "Trilocale nuovo" in body
    assert "Vecchio annuncio" not in body
    assert f"{settings.FRONTEND_URL}/listing/" in body
    assert smtp.sent[0]["To"] == "me@example.test"

    # The watermark moved: the same listing isn't mailed twice.
    assert await send_alert_digest() == 0
    assert len(smtp.sent) == 1


async def test_paused_alert_is_not_mailed(alert, smtp, db_session):
    alert.is_active = False
    await db_session.commit()
    assert await send_alert_digest() == 0
    assert smtp.sent == []


async def test_failed_send_keeps_the_watermark(alert, smtp, monkeypatch, db_session):
    def down(self, msg):
        raise smtplib.SMTPException("server down")

    monkeypatch.setattr(FakeSMTP, "send_message", down)
    alert_id = alert.id
    with pytest.raises(smtplib.SMTPException):
        await send_alert_digest()

    db_session.expire_all()
    assert (await db_session.get(SearchAlert, alert_id)).last_notified_at is None
