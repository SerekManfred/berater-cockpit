"""Passwörter (Argon2), Sitzungs-Token, TOTP und Verschlüsselung des TOTP-Geheimnisses."""
import base64
import hashlib
import hmac
import io
import secrets

import pyotp
import qrcode
import qrcode.image.svg
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken

from app import config

_ph = PasswordHasher()
# Vergleichshash, damit unbekannte E-Mail-Adressen genauso lange brauchen wie bekannte
VERGLEICHS_HASH = _ph.hash(secrets.token_urlsafe(16))


def schluessel_pruefen() -> bytes:
    if len(config.SECRET_KEY) < 32:
        raise RuntimeError("SECRET_KEY fehlt in der .env oder ist kürzer als 32 Zeichen")
    return config.SECRET_KEY.encode()


def passwort_hash(passwort: str) -> str:
    return _ph.hash(passwort)


def passwort_pruefen(hash_: str, passwort: str) -> bool:
    try:
        return _ph.verify(hash_, passwort)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def startpasswort() -> str:
    """Zufälliges Startpasswort, 16 Zeichen ohne verwechselbare Zeichen (0/O, 1/l/I)."""
    zeichen = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(zeichen) for _ in range(16))


def neues_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hmac.new(schluessel_pruefen(), b"sitzung:" + token.encode(), hashlib.sha256).hexdigest()


def _fernet() -> Fernet:
    abgeleitet = hashlib.sha256(b"totp-verschluesselung:" + schluessel_pruefen()).digest()
    return Fernet(base64.urlsafe_b64encode(abgeleitet))


def verschluesseln(text: str) -> str:
    return _fernet().encrypt(text.encode()).decode()


def entschluesseln(text: str) -> str | None:
    try:
        return _fernet().decrypt(text.encode()).decode()
    except InvalidToken:
        return None


def totp_neu() -> str:
    return pyotp.random_base32()


def totp_pruefen(geheimnis: str | None, code: str) -> bool:
    code = (code or "").replace(" ", "")
    if not geheimnis or len(code) != 6 or not code.isdigit():
        return False
    return pyotp.TOTP(geheimnis).verify(code, valid_window=1)


def totp_uri(geheimnis: str, email: str) -> str:
    return pyotp.TOTP(geheimnis).provisioning_uri(name=email, issuer_name="Berater-Cockpit")


def qr_svg(text: str) -> str:
    bild = qrcode.make(text, image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=2)
    puffer = io.BytesIO()
    bild.save(puffer)
    return puffer.getvalue().decode()
