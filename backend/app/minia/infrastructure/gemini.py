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

import httpx

from app.minia.domain.errors import CONTEXT_TOO_LARGE, UNAVAILABLE, MiniaError

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


class GeminiModel:
    provider = 'gemini'
    remote = True

    def __init__(self, model_name, tier=FREE, api_key=None, transport=None, timeout=300.0,
                 max_input_bytes=MAX_INPUT_BYTES):
        if tier not in (FREE, PAID):
            raise ValueError(f'MINIA_GEMINI_TIER invalide : {tier} (free ou paid).')
        self.model_name, self.max_input_bytes = model_name, max_input_bytes
        # Au niveau gratuit, les donnees envoyees peuvent servir a Google ; au niveau payant, non.
        self.data_use = tier == FREE
        self._key = api_key
        self._client = httpx.Client(timeout=timeout, transport=transport)

    def capacity(self, system):
        """Octets disponibles pour le message de l'utilisateur avec ces consignes."""
        return self.max_input_bytes - len(system.encode('utf-8'))

    def _headers(self):
        key = self._key or os.getenv('GEMINI_API_KEY', '').strip()
        if not key:
            raise MiniaError(UNAVAILABLE, 'Minia Gemini n’a pas de clé : définir GEMINI_API_KEY.')
        return {'x-goog-api-key': key, 'Content-Type': 'application/json'}

    def _body(self, system, user):
        size = len(user.encode('utf-8'))
        if size > self.capacity(system):
            raise MiniaError(CONTEXT_TOO_LARGE, f'La demande dépasse la place réservée à Minia Gemini ({size} '
                             f'octets pour {max(self.capacity(system), 0)} disponibles) : réduire la sélection.')
        return {'systemInstruction': {'parts': [{'text': system}]},
                'contents': [{'role': 'user', 'parts': [{'text': user}]}],
                'generationConfig': {'temperature': 0, 'maxOutputTokens': MAX_OUTPUT_TOKENS,
                                     'responseMimeType': 'application/json', 'responseSchema': ANSWER_SCHEMA}}

    def _url(self, method):
        return f'{API_URL}/models/{self.model_name}:{method}'

    def complete(self, system, user):
        body, headers = self._body(system, user), self._headers()
        try:
            response = self._client.post(self._url('generateContent'), json=body, headers=headers)
        except httpx.HTTPError as exc:
            raise _unreachable() from exc
        _check(response, self.model_name)
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
        try:
            with self._client.stream('POST', self._url('streamGenerateContent') + '?alt=sse', json=body,
                                     headers=headers) as response:
                if response.status_code != 200:
                    response.read()
                    _check(response, self.model_name)
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
        raise MiniaError(UNAVAILABLE, f'Modèle Gemini inconnu : {model_name} (MINIA_GEMINI_MODEL).')
    if response.status_code == 429:
        raise MiniaError(UNAVAILABLE, 'Quota de l’API Gemini atteint (niveau gratuit limité) : réessayer plus tard.')
    if response.status_code == 400:
        raise MiniaError(UNAVAILABLE, f'Requête refusée par l’API Gemini : {message or "requête invalide"}')
    raise MiniaError(UNAVAILABLE, f'L’API Gemini a répondu {response.status_code}.')
