"""Transactional email. Messages contain a link and fixed text only: never data values,
never the recipient's data, never secrets other than the single-use link token itself."""
from __future__ import annotations

import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

from nazeer_api.config import Settings

log = logging.getLogger("nazeer_api.mail")


@dataclass
class Mail:
    to: str
    subject: str
    text: str
    kind: str


class Mailer:
    def send(self, mail: Mail) -> None:  # pragma: no cover - interface
        raise NotImplementedError


class MemoryMailer(Mailer):
    """Tests and local development without SMTP."""

    def __init__(self) -> None:
        self.outbox: list[Mail] = []

    def send(self, mail: Mail) -> None:
        self.outbox.append(mail)


class SmtpMailer(Mailer):
    def __init__(self, settings: Settings) -> None:
        self.s = settings

    def send(self, mail: Mail) -> None:
        msg = EmailMessage()
        msg["From"] = self.s.smtp_from
        msg["To"] = mail.to
        msg["Subject"] = mail.subject
        msg.set_content(mail.text, charset="utf-8")
        try:
            with smtplib.SMTP(self.s.smtp_host, self.s.smtp_port, timeout=15) as smtp:
                if self.s.smtp_starttls:
                    smtp.starttls()
                if self.s.smtp_user:
                    smtp.login(self.s.smtp_user, self.s.smtp_password or "")
                smtp.send_message(msg)
            log.info("mail sent: kind=%s", mail.kind)
        except Exception:  # noqa: BLE001 - mail must never break the request; logged without values
            log.error("mail failed: kind=%s", mail.kind, exc_info=True)


def make_mailer(settings: Settings) -> Mailer:
    return SmtpMailer(settings) if settings.mail_backend == "smtp" else MemoryMailer()


# ---------------------------------------------------------------- templates (Arabic first)

FOOTER = "\n\n—\nنَظير · Nazeer\nإن لم تطلب هذه الرسالة فتجاهلها."


def verify_email(base_url: str, to: str, token: str) -> Mail:
    link = f"{base_url}/verify-email?token={token}"
    return Mail(to, "تأكيد بريدك الإلكتروني في نَظير",
                f"مرحباً،\n\nلتأكيد بريدك الإلكتروني افتح الرابط التالي (صالح 48 ساعة):\n{link}{FOOTER}",
                "verify_email")


def reset_password(base_url: str, to: str, token: str) -> Mail:
    link = f"{base_url}/reset-password?token={token}"
    return Mail(to, "إعادة تعيين كلمة المرور في نَظير",
                f"مرحباً،\n\nلإعادة تعيين كلمة المرور افتح الرابط التالي (صالح ساعة واحدة):\n{link}{FOOTER}",
                "reset_password")


def invitation(base_url: str, to: str, org_name: str, token: str) -> Mail:
    link = f"{base_url}/invite?token={token}"
    return Mail(to, f"دعوة للانضمام إلى {org_name} في نَظير",
                f"مرحباً،\n\nدعتك منشأة «{org_name}» للانضمام إلى مساحتها في نَظير.\n"
                f"لقبول الدعوة افتح الرابط التالي (صالح 7 أيام):\n{link}{FOOTER}",
                "invitation")
