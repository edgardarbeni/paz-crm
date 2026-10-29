import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pyotp
import pytest

from app.core.crypto import BlindIndexer
from app.core.errors import ForbiddenError
from app.core.mail import (
    ConsoleMailer,
    MemoryMailer,
    OutgoingEmail,
    SmtpMailer,
    build_mailer,
    send_safely,
)
from app.core.modules import permission_codes
from app.modules.identity import emails
from app.modules.identity.models import Role
from app.modules.identity.permissions import Perm
from app.modules.identity.security import recovery_codes, totp
from app.modules.identity.security.passwords import Passwords, WeakPasswordError
from app.modules.identity.security.tokens import (
    InvalidTokenError,
    TokenScope,
    TokenService,
    hash_opaque_token,
    new_opaque_token,
)
from app.modules.identity.services.access import Access, ensure_can_grant
from tests.support import make_settings

SETTINGS = make_settings()


# --- tokens ------------------------------------------------------------------------------


def test_access_token_roundtrip() -> None:
    service = TokenService(SETTINGS)
    user_id, session_id = uuid.uuid4(), uuid.uuid4()
    token = service.issue_access(
        user_id=user_id, session_id=session_id, scope=TokenScope.FULL, auth_methods=["pwd", "otp"]
    )
    claims = service.decode_access(token)
    assert (claims.user_id, claims.session_id, claims.scope) == (
        user_id,
        session_id,
        TokenScope.FULL,
    )
    assert claims.auth_methods == ("pwd", "otp")


def _forge(**overrides: Any) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "iss": "pazos",
        "aud": "pazos-api",
        "sub": str(uuid.uuid4()),
        "sid": str(uuid.uuid4()),
        "typ": "access",
        "scope": "full",
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    payload.update(overrides)
    secret = overrides.pop("_secret", SETTINGS.jwt_secret.get_secret_value())
    payload.pop("_secret", None)
    return jwt.encode(payload, secret, algorithm="HS256")


@pytest.mark.parametrize(
    "token",
    [
        _forge(exp=datetime.now(UTC) - timedelta(seconds=1)),
        _forge(aud="otra-api"),
        _forge(iss="otro"),
        _forge(typ="mfa_challenge"),
        _forge(sub="no-es-uuid"),
        _forge(scope="admin"),
        _forge(_secret="un-secreto-distinto-de-32-bytes!!"),
        jwt.encode({"sub": "x"}, "k" * 32, algorithm="HS256"),
        "basura",
    ],
)
def test_access_token_rejections(token: str) -> None:
    with pytest.raises(InvalidTokenError):
        TokenService(SETTINGS).decode_access(token)


def test_alg_none_is_rejected() -> None:
    unsigned = jwt.encode({"sub": str(uuid.uuid4()), "typ": "access"}, key="", algorithm="none")
    with pytest.raises(InvalidTokenError):
        TokenService(SETTINGS).decode_access(unsigned)


def test_mfa_challenge_roundtrip_and_type_confusion() -> None:
    service = TokenService(SETTINGS)
    user_id = uuid.uuid4()
    assert service.decode_mfa_challenge(service.issue_mfa_challenge(user_id=user_id)) == user_id
    access = service.issue_access(
        user_id=user_id, session_id=uuid.uuid4(), scope=TokenScope.FULL, auth_methods=["pwd"]
    )
    with pytest.raises(InvalidTokenError):
        service.decode_mfa_challenge(access)
    with pytest.raises(InvalidTokenError):
        service.decode_mfa_challenge(_forge(typ="mfa_challenge", sub="x"))


def test_opaque_tokens() -> None:
    raw, digest = new_opaque_token()
    assert len(raw) >= 43
    assert hash_opaque_token(raw) == digest
    assert new_opaque_token()[0] != raw


# --- TOTP --------------------------------------------------------------------------------


def test_totp_window_and_replay() -> None:
    secret = totp.new_secret()
    now = datetime(2026, 10, 24, 12, 0, 15, tzinfo=UTC)
    code = pyotp.TOTP(secret).at(now)
    step = totp.verify(secret, code, last_used_step=None, at=now)
    assert step is not None
    assert totp.verify(secret, code, last_used_step=step, at=now) is None  # replay
    previous = pyotp.TOTP(secret).at(now - timedelta(seconds=30))
    assert totp.verify(secret, previous, last_used_step=None, at=now) == step - 1  # clock skew
    too_old = pyotp.TOTP(secret).at(now - timedelta(seconds=90))
    assert totp.verify(secret, too_old, last_used_step=None, at=now) is None
    assert totp.verify(secret, f" {code[:3]} {code[3:]} ", last_used_step=None, at=now) == step


@pytest.mark.parametrize("code", ["", "12345", "1234567", "abcdef"])
def test_totp_rejects_malformed_codes(code: str) -> None:
    assert totp.verify(totp.new_secret(), code, last_used_step=None) is None


def test_totp_provisioning_and_qr() -> None:
    uri = totp.provisioning_uri("JBSWY3DPEHPK3PXP", account="ana@example.com", issuer="PAZOS")
    assert uri.startswith("otpauth://totp/PAZOS:ana%40example.com?secret=JBSWY3DPEHPK3PXP")
    assert "issuer=PAZOS" in uri
    assert totp.qr_svg_data_uri(uri).startswith("data:image/svg+xml")


def test_recovery_codes() -> None:
    codes = recovery_codes.generate()
    assert len(codes) == 10
    assert len(set(codes)) == 10
    assert all(len(code) == 19 and code.count("-") == 3 for code in codes)
    assert not any(ch in "".join(codes) for ch in "01ILOU")
    indexer = BlindIndexer(b"k" * 32)
    code = codes[0]
    assert recovery_codes.hash_code(indexer, code) == recovery_codes.hash_code(
        indexer, code.lower().replace("-", " ")
    )


# --- passwords ---------------------------------------------------------------------------


def test_password_hash_verify_and_rehash() -> None:
    passwords = Passwords(SETTINGS)
    hashed = passwords.hash("frase-larga-de-prueba")
    assert hashed.startswith("$argon2id$")
    assert passwords.verify(hashed, "frase-larga-de-prueba")
    assert not passwords.verify(hashed, "otra")
    assert not passwords.verify(None, "frase-larga-de-prueba")
    assert not passwords.verify("no-es-un-hash", "x")
    stronger = Passwords(make_settings(argon2_time_cost=2))
    assert stronger.needs_rehash(hashed)


@pytest.mark.parametrize(
    ("password", "message"),
    [
        ("corta", "al menos 12"),
        ("x" * 129, "exceder 128"),
        ("abababababab", "repetitiva"),
        ("mariana.lopez-2026", "correo"),
    ],
)
def test_password_policy(password: str, message: str) -> None:
    with pytest.raises(WeakPasswordError, match=message):
        Passwords(SETTINGS).validate(password, email="mariana.lopez@example.com")


def test_password_policy_accepts_passphrases() -> None:
    Passwords(SETTINGS).validate("correcto caballo batería grapa", email="ana@example.com")


# --- access rules ------------------------------------------------------------------------


def _role(**kwargs: Any) -> Role:
    return Role(code="r", name="R", **kwargs)


def test_access_rules() -> None:
    plain = Access(roles=(_role(),), permissions=frozenset({Perm.USER_READ}), grants_all=False)
    assert plain.has(Perm.USER_READ)
    assert not plain.has(Perm.USER_CREATE)
    assert not plain.requires_mfa
    assert plain.effective_permissions() == [Perm.USER_READ]

    mfa = Access(roles=(_role(requires_mfa=True),), permissions=frozenset(), grants_all=False)
    assert mfa.requires_mfa
    root = Access(roles=(_role(grants_all=True),), permissions=frozenset(), grants_all=True)
    assert root.requires_mfa
    assert root.has("anything.at.all")
    assert root.effective_permissions() == sorted(permission_codes())

    ensure_can_grant(root, ["audit.log.read"])
    ensure_can_grant(plain, [Perm.USER_READ])
    with pytest.raises(ForbiddenError, match=r"audit\.log\.read"):
        ensure_can_grant(plain, ["audit.log.read"])


# --- e-mail ------------------------------------------------------------------------------


def test_email_templates_escape_and_link() -> None:
    invitation = emails.invitation(
        base_url="https://panel.example.com/",
        to="a@example.com",
        full_name="<b>Ana</b>",
        token="tok/en+1",
        ttl=timedelta(hours=72),
    )
    assert "https://panel.example.com/aceptar-invitacion?token=tok/en%2B1" in invitation.text
    assert "&lt;b&gt;Ana&lt;/b&gt;" in (invitation.html or "")
    assert "72 horas" in invitation.text
    reset = emails.password_reset(
        base_url="https://panel.example.com",
        to="a@example.com",
        full_name="Ana",
        token="t",
        ttl=timedelta(minutes=30),
    )
    assert "30 minutos" in reset.text
    assert "/restablecer-contrasena?token=t" in reset.text


async def test_mail_backends(monkeypatch: pytest.MonkeyPatch) -> None:
    message = OutgoingEmail(to="a@example.com", subject="Hola", text="Texto", html="<p>Texto</p>")
    assert isinstance(build_mailer(make_settings(mail_backend="memory")), MemoryMailer)
    assert isinstance(build_mailer(make_settings(mail_backend="console")), ConsoleMailer)
    await ConsoleMailer().send(message)

    sent: list[Any] = []

    async def fake_send(msg: Any, **kwargs: Any) -> None:
        sent.append((msg, kwargs))

    monkeypatch.setattr("app.core.mail.aiosmtplib.send", fake_send)
    smtp = build_mailer(make_settings(mail_backend="smtp", smtp_host="mailpit", smtp_password="s"))
    assert isinstance(smtp, SmtpMailer)
    assert await send_safely(smtp, message)
    mime, options = sent[0]
    assert mime["Subject"] == "Hola"
    assert mime.is_multipart()
    assert (options["hostname"], options["password"]) == ("mailpit", "s")

    async def broken(msg: Any, **kwargs: Any) -> None:
        raise OSError("smtp down")

    monkeypatch.setattr("app.core.mail.aiosmtplib.send", broken)
    assert not await send_safely(smtp, message)
