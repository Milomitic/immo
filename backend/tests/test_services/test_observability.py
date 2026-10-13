import app.observability as obs
from app.config import settings


def test_sentry_is_off_without_dsn(monkeypatch):
    calls = []
    monkeypatch.setattr(obs.sentry_sdk, "init", lambda **kw: calls.append(kw))
    monkeypatch.setattr(settings, "SENTRY_DSN", "")
    obs.init_sentry("api")
    assert calls == []


def test_sentry_init_with_dsn(monkeypatch):
    calls, tags = [], []
    monkeypatch.setattr(obs.sentry_sdk, "init", lambda **kw: calls.append(kw))
    monkeypatch.setattr(obs.sentry_sdk, "set_tag", lambda k, v: tags.append((k, v)))
    monkeypatch.setattr(settings, "SENTRY_DSN", "https://key@sentry.example/1")
    monkeypatch.setattr(settings, "SENTRY_ENVIRONMENT", "production")
    obs.init_sentry("scraper")
    assert calls == [{
        "dsn": "https://key@sentry.example/1",
        "environment": "production",
        "traces_sample_rate": 0.0,
        "send_default_pii": False,
    }]
    assert tags == [("component", "scraper")]
