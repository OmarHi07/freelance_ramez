"""Email settings: Resend's HTTPS API in production, local backends everywhere else.

Railway Hobby blocks outbound SMTP, so production sends through Anymail's Resend
backend. Each test executes a settings module from scratch, as Django does at
startup, under a controlled environment. Nothing here sends email or touches the
network, and the local ``.env`` file is not re-read.
"""

import importlib.util
import sys

import environ
import pytest
from anymail.backends.resend import EmailBackend as ResendBackend
from django.apps import apps
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import get_connection

RESEND_BACKEND = "anymail.backends.resend.EmailBackend"
CONSOLE_BACKEND = "django.core.mail.backends.console.EmailBackend"
FAKE_KEY = "test-resend-key-not-real"
PRODUCTION_ENV = {
    "DJANGO_SECRET_KEY": "test-only-production-key-0123456789abcdefghijklmnopqrstuvwxyz",
    "DJANGO_ALLOWED_HOSTS": "shop.example.test",
    "DATABASE_URL": "postgres://user:password@localhost:5432/shop",
    "RESEND_API_KEY": FAKE_KEY,
    "DEFAULT_FROM_EMAIL": "rawnaq_accessories1 <onboarding@resend.dev>",
    "EMAIL_TIMEOUT": None,
    "EMAIL_URL": None,
}


def load_settings(monkeypatch, name: str, **environment):
    """Execute ``config.settings.<name>`` afresh; a ``None`` value unsets that variable.

    The fresh modules replace the cached ones in ``sys.modules`` for this test
    only, so the settings the test run itself uses are never touched.
    """
    # .env was applied when the test settings loaded; skip it so it cannot
    # refill a variable this test removed.
    monkeypatch.setattr(environ.Env, "read_env", classmethod(lambda cls, *args, **kwargs: None))
    for key, value in environment.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    module = None
    for module_name in ("config.settings.base", f"config.settings.{name}"):
        spec = importlib.util.find_spec(module_name)
        module = importlib.util.module_from_spec(spec)
        # Environment modules star-import base, so they must find the fresh one.
        monkeypatch.setitem(sys.modules, module_name, module)
        spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Production: Resend's HTTPS API
# ---------------------------------------------------------------------------
def test_production_sends_email_through_resend(monkeypatch):
    production = load_settings(monkeypatch, "production", **PRODUCTION_ENV)
    assert production.EMAIL_BACKEND == RESEND_BACKEND
    assert "anymail" in production.INSTALLED_APPS
    # The test run shares base's INSTALLED_APPS, so the app really loads.
    assert apps.is_installed("anymail")


def test_production_reads_the_resend_key_from_the_environment(monkeypatch, settings):
    production = load_settings(monkeypatch, "production", **PRODUCTION_ENV)
    assert production.ANYMAIL["RESEND_API_KEY"] == FAKE_KEY

    # The backend Django builds from these settings carries the key. Building it sends nothing.
    settings.EMAIL_BACKEND = production.EMAIL_BACKEND
    settings.ANYMAIL = production.ANYMAIL
    connection = get_connection()
    assert isinstance(connection, ResendBackend)
    assert connection.api_key == FAKE_KEY


def test_production_bounds_every_send_by_email_timeout(monkeypatch, settings):
    production = load_settings(monkeypatch, "production", **{**PRODUCTION_ENV, "EMAIL_TIMEOUT": "7"})
    assert production.ANYMAIL["REQUESTS_TIMEOUT"] == 7

    # Password reset asks for a connection without a timeout of its own.
    settings.EMAIL_BACKEND = production.EMAIL_BACKEND
    settings.ANYMAIL = production.ANYMAIL
    assert get_connection().timeout == 7


@pytest.mark.parametrize("value", [None, "", "   "], ids=["missing", "empty", "blank"])
def test_production_refuses_to_start_without_a_resend_key(monkeypatch, value):
    with pytest.raises(ImproperlyConfigured, match="RESEND_API_KEY"):
        load_settings(monkeypatch, "production", **{**PRODUCTION_ENV, "RESEND_API_KEY": value})


@pytest.mark.parametrize("value", [None, "", "   "], ids=["missing", "empty", "blank"])
def test_production_refuses_to_start_without_a_sender_address(monkeypatch, value):
    with pytest.raises(ImproperlyConfigured, match="DEFAULT_FROM_EMAIL"):
        load_settings(monkeypatch, "production", **{**PRODUCTION_ENV, "DEFAULT_FROM_EMAIL": value})


def test_production_takes_the_sender_from_the_environment(monkeypatch):
    sender = "rawnaq_accessories1 <orders@shop.example.test>"
    production = load_settings(monkeypatch, "production", **{**PRODUCTION_ENV, "DEFAULT_FROM_EMAIL": sender})
    assert sender == production.DEFAULT_FROM_EMAIL == production.SERVER_EMAIL


def test_production_never_reads_email_url(monkeypatch):
    smtp_url = "smtp+tls://user:app-password@smtp.example.test:587"
    production = load_settings(monkeypatch, "production", **{**PRODUCTION_ENV, "EMAIL_URL": smtp_url})
    assert production.EMAIL_BACKEND == RESEND_BACKEND
    for smtp_setting in ("EMAIL_HOST", "EMAIL_PORT", "EMAIL_HOST_USER", "EMAIL_HOST_PASSWORD", "EMAIL_USE_TLS"):
        assert not hasattr(production, smtp_setting), smtp_setting


# ---------------------------------------------------------------------------
# Development and tests: local backends, no Resend key
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("email_url", "backend"),
    [
        ("consolemail://", CONSOLE_BACKEND),
        (None, CONSOLE_BACKEND),  # the default
        ("smtp://localhost:1025", "django.core.mail.backends.smtp.EmailBackend"),  # e.g. a local mail catcher
    ],
)
def test_development_uses_the_backend_from_email_url(monkeypatch, email_url, backend):
    development = load_settings(monkeypatch, "development", EMAIL_URL=email_url, RESEND_API_KEY=None)
    assert backend == development.EMAIL_BACKEND
    assert not hasattr(development, "ANYMAIL")


def test_development_ignores_a_resend_key(monkeypatch):
    """A production key copied into .env must not make local runs send real email."""
    development = load_settings(monkeypatch, "development", EMAIL_URL="consolemail://", RESEND_API_KEY=FAKE_KEY)
    assert development.EMAIL_BACKEND == CONSOLE_BACKEND
    assert not hasattr(development, "ANYMAIL")


def test_the_test_suite_only_uses_the_local_outbox(settings):
    assert settings.EMAIL_BACKEND == "django.core.mail.backends.locmem.EmailBackend"
    assert not hasattr(settings, "ANYMAIL")
