"""Adaptateur Gemini de Minia (API Gemini de Google, REST).

Minia Gemini fait le meme travail que Minia Ollama et Minia Claude : memes consignes, meme contexte borne,
meme reponse validee par Taxo. Gemini est un service distant (`remote = True`) : ce que Minia recoit quitte
la machine de Taxo. Au niveau gratuit de l'API, Google peut en outre utiliser les donnees envoyees pour
ameliorer ses produits (`data_use = True`) : le portail le dit, et le diff reste decoche par defaut.

La reponse est contrainte par un schema (sortie JSON structuree). La cle vient de l'environnement
(GEMINI_API_KEY), jamais du code ni du depot.
"""
import json
import os
import time

import httpx

from app.minia.domain.errors import CONTEXT_TOO_LARGE, UNAVAILABLE, MiniaError
from app.minia.infrastructure import retrying
from app.minia.infrastructure.retrying import RETRIES

API_URL = 'https://generativelanguage.googleapis.com/v1beta'
MAX_OUTPUT_TOKENS = 8192
# Comme pour Claude : la fenetre de Gemini est bien plus grande, Minia s'en tient a ses propres limites.
MAX_INPUT_BYTES = 400_000
FREE, PAID = 'free', 'paid'

ANSWER_SCHEMA = {
    'type': 'OBJECT',
    'properties': {
        'cited': {'type': 'ARRAY', 'items': {'type': 'STRING'}},
        'answer': {'type': 'STRING'},
        'unknown': {'type': 'STRING'},
    },
    'required': ['cited', 'answer', 'unknown'],
}
# Fins de generation qui ne sont pas une reponse complete.
_CUT = {'MAX_TOKENS'}
_DECLINED = {'SAFETY', 'RECITATION', 'BLOCKLIST', 'PROHIBITED_CONTENT', 'SPII', 'LANGUAGE', 'OTHER'}


def gemini_schema(schema):
    """Un JSON Schema dans la forme que l'API Gemini attend (types en majuscules, sans additionalProperties)."""
    if isinstance(schema, list):
        return [gemini_schema(item) for item in schema]
    if not isinstance(schema, dict):
        return schema
    converted = {}
    for key, value in schema.items():
        if key == 'additionalProperties':
            continue
        if key == 'type':
            converted[key] = value.upper()
        elif key in ('properties',):
            converted[key] = {name: gemini_schema(item) for name, item in value.items()}
        else:
            converted[key] = gemini_schema(value)
    return converted


class GeminiModel:
    provider = 'gemini'
    remote = True
    # Sait mener l'exploration de MINIA-09 : demander les operations de Taxo une par une (ADR 0009).
    explores = True

    def __init__(self, model_name, tier=FREE, api_key=None, transport=None, timeout=300.0,
                 max_input_bytes=MAX_INPUT_BYTES, sleep=time.sleep):
        if tier not in (FREE, PAID):
            raise ValueError(f'MINIA_GEMINI_TIER invalide : {tier} (free ou paid).')
        self.model_name, self.max_input_bytes = model_name, max_input_bytes
        # Au niveau gratuit, les donnees envoyees peuvent servir a Google ; au niveau payant, non.
        self.data_use = tier == FREE
        self._key, self._sleep = api_key, sleep
        self._client = httpx.Client(timeout=timeout, transport=transport)

    def capacity(self, system):
        """Octets disponibles pour le message de l'utilisateur avec ces consignes."""
        return self.max_input_bytes - len(system.encode('utf-8'))

    def _headers(self):
        key = self._key or os.getenv('GEMINI_API_KEY', '').strip()
        if not key:
            raise MiniaError(UNAVAILABLE, 'Minia Gemini n’a pas de clé : définir GEMINI_API_KEY.')
        return {'x-goog-api-key': key, 'Content-Type': 'application/json'}

    def _body(self, system, user, schema=None):
        size = len(user.encode('utf-8'))
        if size > self.capacity(system):
            raise MiniaError(CONTEXT_TOO_LARGE, f'La demande dépasse la place réservée à Minia Gemini ({size} '
                             f'octets pour {max(self.capacity(system), 0)} disponibles) : réduire la sélection.')
        return {'systemInstruction': {'parts': [{'text': system}]},
                'contents': [{'role': 'user', 'parts': [{'text': user}]}],
                'generationConfig': {'temperature': 0, 'maxOutputTokens': MAX_OUTPUT_TOKENS,
                                     'responseMimeType': 'application/json',
                                     'responseSchema': gemini_schema(schema) if schema else ANSWER_SCHEMA}}

    def _url(self, method):
        return f'{API_URL}/models/{self.model_name}:{method}'

    def _open(self, url, body, headers, stream):
        """Reponse 200 de l'API ; une erreur passagere (surcharge 503, reseau...) est reessayee."""
        return retrying.send(self._client, url, body, headers, stream, self._sleep,
                             lambda response: _check(response, self.model_name), _unreachable)

    def complete(self, system, user, schema=None):
        """Texte de la reponse, contraint par `schema` (JSON Schema) ; par defaut, la reponse de Minia."""
        body, headers = self._body(system, user, schema), self._headers()
        response = self._open(self._url('generateContent'), body, headers, stream=False)
        try:
            part = response.json()
        except ValueError as exc:
            raise MiniaError(UNAVAILABLE, 'Réponse de Gemini illisible.') from exc
        text, finish = _text(part)
        _accepted(part, finish)
        return text

    def stream(self, system, user):
        """Morceaux de la reponse, au fur et a mesure que Gemini les produit ; rend enfin le modele qui a
        repondu (version exacte, quand l'API la donne)."""
        body, headers = self._body(system, user), self._headers()
        served, finish, last = None, None, {}
        response = self._open(self._url('streamGenerateContent') + '?alt=sse', body, headers, stream=True)
        try:
            for line in response.iter_lines():
                if not line.startswith('data:'):
                    continue
                try:
                    last = json.loads(line[5:])
                except ValueError as exc:
                    raise MiniaError(UNAVAILABLE, 'Réponse de Gemini illisible.') from exc
                text, finish = _text(last, finish)
                served = last.get('modelVersion') or served
                # Le morceau qui porte un refus ou une coupure n'est jamais diffuse. Les morceaux deja
                # diffuses ne sont qu'un brouillon provisoire, que le portail efface a l'echec.
                _accepted(last, finish)
                if text:
                    yield text
        except httpx.HTTPError as exc:
            raise _unreachable() from exc
        finally:
            response.close()
        return served or self.model_name


def _text(part, finish=None):
    """Texte d'un morceau de reponse, et la raison de fin s'il la donne."""
    candidates = part.get('candidates') or [{}]
    candidate = candidates[0] if isinstance(candidates[0], dict) else {}
    parts = (candidate.get('content') or {}).get('parts') or []
    text = ''.join(item.get('text', '') for item in parts if isinstance(item, dict) and not item.get('thought'))
    return text, candidate.get('finishReason') or finish


def _accepted(part, finish):
    """Une reponse bloquee, declinee ou coupee n'est pas une reponse : Taxo le dit."""
    blocked = (part.get('promptFeedback') or {}).get('blockReason')
    if blocked or finish in _DECLINED:
        raise MiniaError(UNAVAILABLE, 'Gemini a décliné cette demande : reformuler la question.')
    if finish in _CUT:
        raise MiniaError(UNAVAILABLE, 'La réponse de Gemini a été coupée (longueur maximale atteinte).')


def _unreachable():
    return MiniaError(UNAVAILABLE, 'API Gemini injoignable : vérifier la connexion réseau.')


def _check(response, model_name):
    """Erreur de l'API Gemini, dite en clair."""
    if response.status_code == 200:
        return
    try:
        detail = (response.json().get('error') or {})
    except ValueError:
        detail = {}
    message, status = str(detail.get('message', '')), str(detail.get('status', ''))
    said = json.dumps(detail).upper()
    if 'API_KEY' in said or 'API KEY' in said or response.status_code in (401, 403) or status == 'PERMISSION_DENIED':
        raise MiniaError(UNAVAILABLE, 'Clé Gemini refusée : vérifier GEMINI_API_KEY.')
    if response.status_code == 404:
        # Un 404 ne dit pas que le modele n'existe pas : il peut exister sans etre ouvert a ce projet
        # (Google reserve parfois d'anciens modeles aux projets qui les utilisaient deja).
        said = f' Google : « {message} »' if message else ''
        raise MiniaError(UNAVAILABLE, f'Modèle Gemini introuvable ou non accessible avec cette clé : {model_name} '
                         f'(MINIA_GEMINI_MODEL). Choisir un modèle listé pour ce projet dans Google AI Studio.{said}')
    if response.status_code == 503:
        said = f' Google : « {message} »' if message else ''
        raise MiniaError(UNAVAILABLE, f'Gemini est momentanément surchargé (503), même après {RETRIES} nouvelles '
                         f'tentatives : réessayer dans un moment, ou choisir un autre modèle.{said}')
    if response.status_code == 429:
        raise MiniaError(UNAVAILABLE, 'Quota de l’API Gemini atteint (niveau gratuit limité) : réessayer plus tard.')
    if response.status_code == 400:
        raise MiniaError(UNAVAILABLE, f'Requête refusée par l’API Gemini : {message or "requête invalide"}')
    raise MiniaError(UNAVAILABLE, f'L’API Gemini a répondu {response.status_code}.')
