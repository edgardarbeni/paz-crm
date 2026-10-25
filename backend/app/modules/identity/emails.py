"""E-mail templates (es-MX). Links point to panel routes built in phase E."""

from datetime import timedelta
from html import escape
from urllib.parse import quote

from app.core.mail import OutgoingEmail


def _hours(ttl: timedelta) -> str:
    hours = int(ttl.total_seconds() // 3600)
    return f"{hours} horas" if hours >= 2 else f"{int(ttl.total_seconds() // 60)} minutos"


def invitation(
    *, base_url: str, to: str, full_name: str, token: str, ttl: timedelta
) -> OutgoingEmail:
    link = f"{base_url.rstrip('/')}/aceptar-invitacion?token={quote(token)}"
    text = (
        f"Hola {full_name}:\n\n"
        "Te invitaron a PAZOS. Para activar tu cuenta y definir tu contraseña entra a:\n\n"
        f"{link}\n\n"
        f"El enlace vence en {_hours(ttl)}. Si no esperabas esta invitación, ignora este correo."
    )
    html = (
        f"<p>Hola {escape(full_name)}:</p>"
        "<p>Te invitaron a <strong>PAZOS</strong>. Para activar tu cuenta y definir tu "
        f'contraseña, <a href="{escape(link)}">acepta la invitación</a>.</p>'
        f"<p>El enlace vence en {_hours(ttl)}. Si no esperabas esta invitación, ignora este "
        "correo.</p>"
    )
    return OutgoingEmail(to=to, subject="Invitación a PAZOS", text=text, html=html)


def password_reset(
    *, base_url: str, to: str, full_name: str, token: str, ttl: timedelta
) -> OutgoingEmail:
    link = f"{base_url.rstrip('/')}/restablecer-contrasena?token={quote(token)}"
    text = (
        f"Hola {full_name}:\n\n"
        "Recibimos una solicitud para restablecer tu contraseña de PAZOS:\n\n"
        f"{link}\n\n"
        f"El enlace vence en {_hours(ttl)} y solo se puede usar una vez. Si no lo solicitaste, "
        "ignora este correo: tu contraseña no cambiará."
    )
    html = (
        f"<p>Hola {escape(full_name)}:</p>"
        "<p>Recibimos una solicitud para restablecer tu contraseña de <strong>PAZOS</strong>. "
        f'<a href="{escape(link)}">Restablecer contraseña</a>.</p>'
        f"<p>El enlace vence en {_hours(ttl)} y solo se puede usar una vez. Si no lo "
        "solicitaste, ignora este correo.</p>"
    )
    return OutgoingEmail(to=to, subject="Restablecer contraseña de PAZOS", text=text, html=html)
