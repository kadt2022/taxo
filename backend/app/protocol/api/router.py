"""Transport HTTP du protocole Taxo (ADR 0009, section 11) : un echange par requete.

Les operations d'une meme requete partagent l'instantane, le budget et les references (`F…`, `E…`).
Chaque operation repond dans l'enveloppe commune ; un refus est un resultat `ERROR`, pas une erreur HTTP.
"""
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.protocol.application.exchange import MAX_EXCHANGE_BYTES, MAX_OPERATIONS
from app.protocol.domain.envelope import PROTOCOL

_ERRORS = {404: {'description': 'Projet introuvable.'},
           409: {'description': 'Aucune analyse globale pour ce projet.'}}


class Consent(BaseModel):
    diff: bool = Field(False, description='Autoriser la lecture des blocs modifiés d’un commit (ADR 0008).')


class Operation(BaseModel):
    protocol: str = PROTOCOL
    operation: str = Field(..., max_length=100)
    arguments: dict[str, Any] = Field(default_factory=dict)
    max_bytes: int | None = None


class ExchangeRequest(BaseModel):
    protocol: str = Field(PROTOCOL, pattern=f'^{PROTOCOL}$')
    consent: Consent = Field(default_factory=Consent)
    max_bytes: int | None = Field(None, ge=1, le=MAX_EXCHANGE_BYTES)
    requests: list[Operation] = Field(..., min_length=1, max_length=MAX_OPERATIONS)


def create_router(taxo_query):
    router = APIRouter()

    @router.post('/api/projects/{project_id}/taxo-query', responses=_ERRORS)
    def exchange(project_id: str, body: ExchangeRequest):
        opened = taxo_query.open(project_id, diff_consent=body.consent.diff, max_bytes=body.max_bytes)
        responses = [opened.call(item.model_dump()) for item in body.requests]
        return {'protocol': PROTOCOL, 'snapshot': opened.snapshot,
                'budget': {'max_bytes': opened.budget, 'used': opened.used}, 'responses': responses}

    return router
