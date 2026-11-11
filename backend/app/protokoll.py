"""Protokoll: jeder Login, Fehlversuch und jede Kontoänderung."""
from fastapi import Request
from sqlalchemy.orm import Session

from app.modelle import Protokoll, jetzt


def client_ip(request: Request | None) -> str | None:
    if request is None:
        return None
    # Kette: Browser -> zentraler Caddy -> cockpit-web -> API. cockpit-web vertraut nur privaten Netzen.
    weitergeleitet = request.headers.get("x-forwarded-for")
    if weitergeleitet:
        return weitergeleitet.split(",")[0].strip()[:64]
    return request.client.host[:64] if request.client else None


def protokollieren(db: Session, request: Request | None, aktion: str, benutzer_id: int | None = None, **details):
    db.add(Protokoll(zeit=jetzt(), benutzer_id=benutzer_id, aktion=aktion, details=details or None, ip=client_ip(request)))
