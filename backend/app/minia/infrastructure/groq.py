"""Adaptateur Groq de Minia (GroqCloud, API compatible OpenAI, REST).

Minia Groq fait le meme travail que les autres fournisseurs : memes consignes, meme contexte borne, meme reponse
validee par Taxo, et le mode exploration (ARCHITECTURE § 12). Groq est un service distant (`remote = True`) : ce que
Minia recoit quitte la machine de Taxo. Groq dit ne conserver aucune donnee d'inference par defaut, mais sa page ne
dit pas si les donnees servent a entrainer des modeles : au niveau gratuit, Taxo le suppose (`data_use = True`, comme
Mistral et Gemini), le portail le dit et le diff reste decoche par defaut.

La reponse est contrainte par un schema JSON (sortie structuree stricte) pour les modeles qui la gerent ; pour les
autres, par un objet JSON dont le schema est redit dans les consignes. La cle vient de l'environnement
(GROQ_API_KEY), jamais du code ni du depot.
"""
import json
import os
import time

import httpx

from app.minia.domain.cancellation import check
from app.minia.domain.errors import CONTEXT_TOO_LARGE, UNAVAILABLE, MiniaError
from app.minia.infrastructure import retrying
from app.minia.infrastructure.calls import client_for
from app.minia.infrastructure.mistral import ANSWER_SCHEMA, _choice, _content
from app.minia.infrastructure.retrying import RETRIES

API_URL = 'https://api.groq.com/openai/v1/chat/completions'
MAX_OUTPUT_TOKENS = 8192
# Fenetre de contexte du modele, en tokens (MINIA_GROQ_NUM_CTX) : par defaut, une valeur prudente que les modeles
# courants depassent. La reponse y a sa place reservee.
DEFAULT_NUM_CTX = 32768
TEMPLATE_TOKENS = 64
FREE, PAID = 'free', 'paid'
# Les modeles qui gerent le schema strict (documentation de Groq) ; les autres ne garantissent que du JSON valide.
STRICT_MODELS = frozenset({'openai/gpt-oss-20b', 'openai/gpt-oss-120b', 'qwen/qwen3.8-27b'})
_CUT = {'length'}
_FAILED = {'error'}
_SCHEMA_NOTE = '\n\nReponds par un seul objet JSON conforme a ce schema JSON :\n{}'


class GroqModel:
    provider = 'groq'
    remote = True
    # Sait mener l'exploration de MINIA-09 : demander les operations de Taxo une par une (ARCHITECTURE § 12).
    explores = True

    def __init__(self, model_name, tier=FREE, api_key=None, transport=None, timeout=300.0,
                 num_ctx=DEFAULT_NUM_CTX, sleep=time.sleep):
        if tier not in (FREE, PAID):
            raise ValueError(f'MINIA_GROQ_TIER invalide : {tier} (free ou paid).')
        if num_ctx < 2 * MAX_OUTPUT_TOKENS:
            raise ValueError(f'MINIA_GROQ_NUM_CTX trop petit : {num_ctx} (minimum {2 * MAX_OUTPUT_TOKENS}).')
        self.model_name, self.num_ctx = model_name, num_ctx
        # Au niveau gratuit, Taxo suppose que les donnees envoyees peuvent servir a Groq ; au niveau payant, non.
        self.data_use = tier == FREE
        self._key, self._sleep = api_key, sleep
        self._client = httpx.Client(timeout=timeout, transport=transport)
        # Un appel qu'on peut arreter a son propre client : l'arret le ferme, meme avant la reponse (TAXO-UX-03).
        self._new_client = lambda: httpx.Client(timeout=timeout, transport=transport)

    def capacity(self, system):
        """Octets disponibles pour le message de l'utilisateur avec ces consignes. Borne sure, comme pour les autres
        fournisseurs : un texte ne compte jamais plus de tokens que d'octets UTF-8 ; la reponse garde sa place."""
        return self.num_ctx - TEMPLATE_TOKENS - MAX_OUTPUT_TOKENS - len(system.encode('utf-8'))

    def _headers(self):
        key = self._key or os.getenv('GROQ_API_KEY', '').strip()
        if not key:
            raise MiniaError(UNAVAILABLE, 'Minia Groq n’a pas de clé : définir GROQ_API_KEY.')
        return {'Authorization': f'Bearer {key}', 'Content-Type': 'application/json', 'Accept': 'application/json'}

    def _format(self, system, schema):
        """La contrainte de la reponse et les consignes qui l'accompagnent."""
        if self.model_name in STRICT_MODELS:
            return system, {'type': 'json_schema', 'json_schema': {'name': 'minia', 'schema': schema, 'strict': True}}
        return system + _SCHEMA_NOTE.format(json.dumps(schema, ensure_ascii=False)), {'type': 'json_object'}

    def _body(self, system, user, stream, schema=None):
        size = len(user.encode('utf-8'))
        if size > self.capacity(system):
            raise MiniaError(CONTEXT_TOO_LARGE, f'La demande dépasse la place réservée à Minia Groq ({size} octets '
                             f'pour {max(self.capacity(system), 0)} disponibles) : réduire la sélection ou augmenter '
                             'MINIA_GROQ_NUM_CTX.')
        system, response_format = self._format(system, schema or ANSWER_SCHEMA)
        return {'model': self.model_name, 'temperature': 0, 'max_completion_tokens': MAX_OUTPUT_TOKENS,
                'stream': stream, 'response_format': response_format,
                'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}]}

    def _open(self, body, stream, client=None, cancel=None):
        return retrying.send(client or self._client, API_URL, body, self._headers(), stream, self._sleep,
                             lambda response: _check(response, self.model_name), _unreachable, cancel)

    def complete(self, system, user, schema=None, cancel=None):
        """Texte de la reponse, contraint par `schema` (JSON Schema) ; par defaut, la reponse de Minia. Avec
        un jeton d'arret, la reponse passe par le flux, que l'arret coupe (TAXO-UX-03)."""
        if cancel is not None:
            return ''.join(self.stream(system, user, schema, cancel))
        response = self._open(self._body(system, user, False, schema), stream=False)
        try:
            data = response.json()
        except ValueError as exc:
            raise MiniaError(UNAVAILABLE, 'Réponse de Groq illisible.') from exc
        choice = _choice(data)
        _accepted(choice.get('finish_reason'))
        return _content((choice.get('message') or {}).get('content'))

    def stream(self, system, user, schema=None, cancel=None):
        """Morceaux de la reponse, au fur et a mesure que Groq les produit ; rend enfin le modele qui a repondu."""
        body = self._body(system, user, True, schema)
        with client_for(self._client, self._new_client, cancel) as client:
            return (yield from self._read(client, body, cancel))

    def _read(self, client, body, cancel):
        response = self._open(body, True, client, cancel)
        served = None
        try:
            for line in response.iter_lines():
                check(cancel)
                if not line.startswith('data:'):
                    continue
                payload = line[5:].strip()
                if payload == '[DONE]':
                    break
                try:
                    part = json.loads(payload)
                except ValueError as exc:
                    raise MiniaError(UNAVAILABLE, 'Réponse de Groq illisible.') from exc
                served = part.get('model') or served
                choice = _choice(part)
                # Le morceau qui porte une coupure ou une erreur n'est jamais diffuse ; le raisonnement d'un modele
                # qui reflechit (`reasoning`) n'est jamais transmis : seul `content` compte.
                _accepted(choice.get('finish_reason'))
                text = _content((choice.get('delta') or {}).get('content'))
                if text:
                    yield text
        except (httpx.HTTPError, httpx.StreamError) as exc:
            check(cancel)
            raise _unreachable() from exc
        finally:
            response.close()
        return served or self.model_name


def _accepted(finish):
    """Une reponse coupee ou en erreur n'est pas une reponse : Taxo le dit."""
    if finish in _CUT:
        raise MiniaError(UNAVAILABLE, 'La réponse de Groq a été coupée (longueur maximale atteinte).')
    if finish in _FAILED:
        raise MiniaError(UNAVAILABLE, 'Groq n’a pas pu terminer sa réponse : réessayer.')


def _unreachable():
    return MiniaError(UNAVAILABLE, 'API Groq injoignable : vérifier la connexion réseau.')


def _message(response):
    try:
        detail = response.json()
    except ValueError:
        return ''
    error = detail.get('error') if isinstance(detail, dict) else None
    message = error.get('message') if isinstance(error, dict) else ''
    return message if isinstance(message, str) else ''


def _check(response, model_name):
    """Erreur de l'API Groq, dite en clair."""
    message = _message(response)
    said = f' Groq : « {message} »' if message else ''
    status = response.status_code
    if status in (401, 403):
        raise MiniaError(UNAVAILABLE, 'Clé Groq refusée : vérifier GROQ_API_KEY.')
    if status == 404 or (status == 400 and 'model' in message.lower()):
        raise MiniaError(UNAVAILABLE, f'Modèle Groq introuvable ou non accessible avec cette clé : {model_name} '
                         f'(MINIA_GROQ_MODEL). Choisir un modèle listé pour ce compte.{said}')
    if status == 413:
        raise MiniaError(UNAVAILABLE, 'Demande trop grande pour la limite de tokens du compte Groq (niveau gratuit '
                         f'très limité) : réduire la sélection ou passer au niveau payant.{said}')
    if status == 429:
        raise MiniaError(UNAVAILABLE, 'Quota de l’API Groq atteint (niveau gratuit limité) : réessayer plus tard.'
                         f'{said}')
    if status == 503:
        raise MiniaError(UNAVAILABLE, f'Groq est momentanément surchargé (503), même après {RETRIES} nouvelles '
                         f'tentatives : réessayer dans un moment, ou choisir un autre modèle.{said}')
    if status in (400, 422):
        raise MiniaError(UNAVAILABLE, f'Requête refusée par l’API Groq : {message or "requête invalide"}')
    raise MiniaError(UNAVAILABLE, f'L’API Groq a répondu {status}.')
