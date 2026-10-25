"""Password hashing (Argon2id) and policy (ASVS V2.1)."""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import Settings
from app.core.errors import BadRequestError

MAX_PASSWORD_LENGTH = 128  # bounds Argon2 work per request


class WeakPasswordError(BadRequestError):
    code = "weak-password"
    title = "Contraseña no válida"


class Passwords:
    def __init__(self, settings: Settings) -> None:
        self._hasher = PasswordHasher(
            time_cost=settings.argon2_time_cost,
            memory_cost=settings.argon2_memory_cost_kib,
            parallelism=settings.argon2_parallelism,
        )
        self._min_length = settings.password_min_length
        # Verified when the account does not exist, so response time does not reveal it.
        self._dummy_hash = self._hasher.hash("paz-dummy-password-for-timing")

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, password_hash: str | None, password: str) -> bool:
        try:
            return self._hasher.verify(password_hash or self._dummy_hash, password) and bool(
                password_hash
            )
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False

    def needs_rehash(self, password_hash: str) -> bool:
        return self._hasher.check_needs_rehash(password_hash)

    def validate(self, password: str, *, email: str | None = None) -> None:
        """Length-based policy (NIST 800-63B / ASVS 2.1): no composition rules."""
        if len(password) < self._min_length:
            raise WeakPasswordError(
                f"La contraseña debe tener al menos {self._min_length} caracteres."
            )
        if len(password) > MAX_PASSWORD_LENGTH:
            raise WeakPasswordError(
                f"La contraseña no puede exceder {MAX_PASSWORD_LENGTH} caracteres."
            )
        if len(set(password)) < 4:
            raise WeakPasswordError("La contraseña es demasiado repetitiva.")
        local_part = (email or "").split("@")[0].lower()
        if len(local_part) >= 4 and local_part in password.lower():
            raise WeakPasswordError("La contraseña no puede contener tu correo.")
