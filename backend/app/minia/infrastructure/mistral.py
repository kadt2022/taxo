"""Adaptateur Mistral de Minia (API La Plateforme de Mistral AI, REST).

Minia Mistral fait le meme travail que les autres fournisseurs : memes consignes, meme contexte borne, meme
reponse validee par Taxo, et le mode exploration (ADR 0009). Mistral est un service distant
(`remote = True`) : ce que Minia recoit quitte la machine de Taxo. Au niveau gratuit, Mistral peut en outre
utiliser les donnees envoyees pour entrainer ses modeles (`data_use = True`) : le portail le dit, et le diff
reste decoche par defaut.

La reponse est contrainte par un schema JSON (sortie structuree). La cle vient de l'environnement
(MISTRAL_API_KEY), jamais du code ni du depot.
"""
import json
import os
import time

import httpx

from app.minia.domain.errors import CONTEXT_TOO_LARGE, UNAVAILABLE, MiniaError
from app.minia.infrastructure import retrying
from app.minia.infrastructure.retrying import RETRIES

API_URL = 'https://api.mistral.ai/v1/chat/completions'
MAX_OUTPUT_TOKENS = 8192
# Fenetre de contexte du modele, en tokens (MINIA_MISTRAL_NUM_CTX) : elle varie d'un modele a l'autre ; par
# defaut, une valeur prudente que les modeles courants depassent. La reponse y a sa place reservee.
DEFAULT_NUM_CTX = 32768
TEMPLATE_TOKENS = 64
FREE, PAID = 'free', 'paid'

ANSWER_SCHEMA = {
    'type': 'object',
    'properties': {
        'cited': {'type': 'array', 'items': {'type': 'string'}},
        'answer': {'type': 'string'},
        'unknown': {'type': 'string'},
    },
    'required': ['cited', 'answer', 'unknown'],
    'additionalProperties': False,
}
# Fins de generation qui ne sont pas une reponse complete.
_CUT = {'length', 'model_length'}
_FAILED = {'error'}


class MistralModel:
    provider = 'mistral'
    remote = True
    # Sait mener l'exploration de MINIA-09 : demander les operations de Taxo une par une (ADR 0009).
    explores = True

    def __init__(self, model_name, tier=FREE, api_key=None, transport=None, timeout=300.0,
                 num_ctx=DEFAULT_NUM_CTX, sleep=time.sleep):
        if tier not in (FREE, PAID):
            raise ValueError(f'MINIA_MISTRAL_TIER invalide : {tier} (free ou paid).')
        if num_ctx < 2 * MAX_OUTPUT_TOKENS:
            raise ValueError(f'MINIA_MISTRAL_NUM_CTX trop petit : {num_ctx} (minimum {2 * MAX_OUTPUT_TOKENS}).')
        self.model_name, self.num_ctx = model_name, num_ctx
        # Au niveau gratuit, les donnees envoyees peuvent servir a Mistral ; au niveau payant, non.
        self.data_use = tier == FREE
        self._key, self._sleep = api_key, sleep
        self._client = httpx.Client(timeout=timeout, transport=transport)

    def capacity(self, system):
        """Octets disponibles pour le message de l'utilisateur avec ces consignes. Borne sure, comme pour
        Ollama : un texte ne compte jamais plus de tokens que d'octets UTF-8 ; la reponse garde sa place."""
        return self.num_ctx - TEMPLATE_TOKENS - MAX_OUTPUT_TOKENS - len(system.encode('utf-8'))

    def _headers(self):
        key = self._key or os.getenv('MISTRAL_API_KEY', '').strip()
        if not key:
            raise MiniaError(UNAVAILABLE, 'Minia Mistral n’a pas de clé : définir MISTRAL_API_KEY.')
        return {'Authorization': f'Bearer {key}', 'Content-Type': 'application/json', 'Accept': 'application/json'}

    def _body(self, system, user, stream, schema=None):
        size = len(user.encode('utf-8'))
        if size > self.capacity(system):
            raise MiniaError(CONTEXT_TOO_LARGE, f'La demande dépasse la place réservée à Minia Mistral ({size} '
                             f'octets pour {max(self.capacity(system), 0)} disponibles) : réduire la sélection ou augmenter '
                             'MINIA_MISTRAL_NUM_CTX.')
        return {'model': self.model_name, 'temperature': 0, 'max_tokens': MAX_OUTPUT_TOKENS, 'stream': stream,
                'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}],
                'response_format': {'type': 'json_schema', 'json_schema': {
                    'name': 'minia', 'schema': schema or ANSWER_SCHEMA, 'strict': True}}}

    def _open(self, body, stream):
        return retrying.send(self._client, API_URL, body, self._headers(), stream, self._sleep,
                             lambda response: _check(response, self.model_name), _unreachable)

    def complete(self, system, user, schema=None):
        """Texte de la reponse, contraint par `schema` (JSON Schema) ; par defaut, la reponse de Minia."""
        response = self._open(self._body(system, user, False, schema), stream=False)
        try:
            data = response.json()
        except ValueError as exc:
            raise MiniaError(UNAVAILABLE, 'Réponse de Mistral illisible.') from exc
        choice = _choice(data)
        _accepted(choice.get('finish_reason'))
        return _content((choice.get('message') or {}).get('content'))

    def stream(self, system, user):
        """Morceaux de la reponse, au fur et a mesure que Mistral les produit ; rend enfin le modele qui a
        repondu, quand l'API le dit."""
        response = self._open(self._body(system, user, True), stream=True)
        served = None
        try:
            for line in response.iter_lines():
                if not line.startswith('data:'):
                    continue
                payload = line[5:].strip()
                if payload == '[DONE]':
                    break
                try:
                    part = json.loads(payload)
                except ValueError as exc:
                    raise MiniaError(UNAVAILABLE, 'Réponse de Mistral illisible.') from exc
                served = part.get('model') or served
                choice = _choice(part)
                # Le morceau qui porte une coupure ou une erreur n'est jamais diffuse. Les morceaux deja
                # diffuses ne sont qu'un brouillon provisoire, que le portail efface a l'echec.
                _accepted(choice.get('finish_reason'))
                text = _content((choice.get('delta') or {}).get('content'))
                if text:
                    yield text
        except httpx.HTTPError as exc:
            raise _unreachable() from exc
        finally:
            response.close()
        return served or self.model_name


def _choice(data):
    choices = data.get('choices') if isinstance(data, dict) else None
    return choices[0] if choices and isinstance(choices[0], dict) else {}


def _content(content):
    """Texte d'un message : une chaine, ou une liste de morceaux dont seuls les textes comptent (le
    raisonnement d'un modele qui reflechit n'est jamais transmis)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return ''.join(item.get('text', '') for item in content if isinstance(item, dict) and item.get('type') == 'text')
    return ''


def _accepted(finish):
    """Une reponse coupee ou en erreur n'est pas une reponse : Taxo le dit."""
    if finish in _CUT:
        raise MiniaError(UNAVAILABLE, 'La réponse de Mistral a été coupée (longueur maximale atteinte).')
    if finish in _FAILED:
        raise MiniaError(UNAVAILABLE, 'Mistral n’a pas pu terminer sa réponse : réessayer.')


def _unreachable():
    return MiniaError(UNAVAILABLE, 'API Mistral injoignable : vérifier la connexion réseau.')


def _message(response):
    try:
        detail = response.json()
    except ValueError:
        return ''
    if not isinstance(detail, dict):
        return ''
    message = detail.get('message') or detail.get('detail') or ''
    return message if isinstance(message, str) else json.dumps(message, ensure_ascii=False)


def _check(response, model_name):
    """Erreur de l'API Mistral, dite en clair."""
    message = _message(response)
    said = f' Mistral : « {message} »' if message else ''
    if response.status_code in (401, 403):
        raise MiniaError(UNAVAILABLE, 'Clé Mistral refusée : vérifier MISTRAL_API_KEY.')
    if response.status_code == 404 or (response.status_code == 400 and 'model' in message.lower()):
        raise MiniaError(UNAVAILABLE, f'Modèle Mistral introuvable ou non accessible avec cette clé : {model_name} '
                         f'(MINIA_MISTRAL_MODEL). Choisir un modèle listé pour ce compte.{said}')
    if response.status_code == 429:
        raise MiniaError(UNAVAILABLE, 'Quota de l’API Mistral atteint (niveau gratuit limité) : réessayer plus tard.')
    if response.status_code == 503:
        raise MiniaError(UNAVAILABLE, f'Mistral est momentanément surchargé (503), même après {RETRIES} nouvelles '
                         f'tentatives : réessayer dans un moment, ou choisir un autre modèle.{said}')
    if response.status_code in (400, 422):
        raise MiniaError(UNAVAILABLE, f'Requête refusée par l’API Mistral : {message or "requête invalide"}')
    raise MiniaError(UNAVAILABLE, f'L’API Mistral a répondu {response.status_code}.')
