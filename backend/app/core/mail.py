"""Outgoing e-mail (D-35). SMTP in every environment (Mailpit in development); an in-memory
backend for tests and a console backend for local runs without SMTP."""

from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol

import aiosmtplib

from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class OutgoingEmail:
    to: str
    subject: str
    text: str
    html: str | None = None


class Mailer(Protocol):
    async def send(self, email: OutgoingEmail) -> None: ...


class SmtpMailer:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def send(self, email: OutgoingEmail) -> None:
        settings = self._settings
        await aiosmtplib.send(
            _to_message(email, sender=settings.mail_from),
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username,
            password=settings.smtp_password.get_secret_value() if settings.smtp_password else None,
            start_tls=settings.smtp_starttls,
            use_tls=settings.smtp_use_tls,
            timeout=15,
        )


class ConsoleMailer:
    async def send(self, email: OutgoingEmail) -> None:
        logger.info("email_console", to=email.to, subject=email.subject, text=email.text)


class MemoryMailer:
    def __init__(self) -> None:
        self.outbox: list[OutgoingEmail] = []

    async def send(self, email: OutgoingEmail) -> None:
        self.outbox.append(email)


def _to_message(email: OutgoingEmail, *, sender: str) -> EmailMessage:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = email.to
    message["Subject"] = email.subject
    message.set_content(email.text)
    if email.html:
        message.add_alternative(email.html, subtype="html")
    return message


def build_mailer(settings: Settings) -> Mailer:
    match settings.mail_backend:
        case "memory":
            return MemoryMailer()
        case "console":
            return ConsoleMailer()
        case _:
            return SmtpMailer(settings)


async def send_safely(mailer: Mailer, email: OutgoingEmail) -> bool:
    """Sends without raising (used from background tasks); failures are logged."""
    try:
        await mailer.send(email)
    except Exception:
        logger.exception("email_send_failed", subject=email.subject)
        return False
    return True
