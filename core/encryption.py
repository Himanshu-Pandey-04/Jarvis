"""
Symmetric encryption for the password vault.
We derive a Fernet key from the user's master password using PBKDF2 (480k iterations).

The master password itself is never stored. We store a verifier:
the encryption of a known plaintext ("workbench-verify"). On unlock,
we attempt to decrypt the verifier; success == correct password.
"""
import base64
import os
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

VERIFIER_PLAINTEXT = "workbench-verify"
PBKDF2_ITERATIONS = 480_000


def derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))


def new_salt() -> str:
    return base64.b64encode(os.urandom(16)).decode("ascii")


def salt_from_str(s: str) -> bytes:
    return base64.b64decode(s.encode("ascii"))


class Vault:
    """A locked-by-default symmetric vault used by the password manager."""

    def __init__(self):
        self._fernet: Fernet | None = None

    @property
    def is_unlocked(self) -> bool:
        return self._fernet is not None

    def unlock(self, password: str, salt_str: str, verifier_token: str) -> bool:
        try:
            key = derive_key(password, salt_from_str(salt_str))
            f = Fernet(key)
            decoded = f.decrypt(verifier_token.encode("ascii")).decode("utf-8")
            if decoded != VERIFIER_PLAINTEXT:
                return False
            self._fernet = f
            return True
        except (InvalidToken, ValueError):
            return False

    def initialize(self, password: str) -> tuple[str, str]:
        """Set up a brand-new vault. Returns (salt_str, verifier_token)."""
        salt_str = new_salt()
        key = derive_key(password, salt_from_str(salt_str))
        f = Fernet(key)
        verifier = f.encrypt(VERIFIER_PLAINTEXT.encode("utf-8")).decode("ascii")
        self._fernet = f
        return salt_str, verifier

    def lock(self):
        self._fernet = None

    def encrypt(self, plaintext: str) -> str:
        if not self._fernet:
            raise RuntimeError("Vault is locked")
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")

    def decrypt(self, token: str) -> str:
        if not self._fernet:
            raise RuntimeError("Vault is locked")
        try:
            return self._fernet.decrypt(token.encode("ascii")).decode("utf-8")
        except InvalidToken:
            return ""
