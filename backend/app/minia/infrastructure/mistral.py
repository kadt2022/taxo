"""Adaptateur Mistral de Minia (API La Plateforme de Mistral AI, REST).

Minia Mistral fait le meme travail que les autres fournisseurs : memes consignes, meme contexte borne, meme
reponse validee par Taxo, et le mode exploration (ARCHITECTURE § 12). Mistral est un service distant
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

from app.minia.domain.cancellation import check
from app.minia.domain.errors import CONTEXT_TOO_LARGE, UNAVAILABLE, MiniaError
from app.minia.infrastructure import retrying
from app.minia.infrastructure.calls import client_for
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
    """Un fournisseur distant a l'API compatible OpenAI ; Groq en reprend tout et ne change que ses constantes
    (`label`, `url`, `key_variable`, `settings_prefix`, `token_field`) et la contrainte de sa reponse."""
    provider = 'mistral'
    label = 'Mistral'
    url = API_URL
    key_variable = 'MISTRAL_API_KEY'
    settings_prefix = 'MINIA_MISTRAL'
    token_field = 'max_tokens'
    remote = True
    # Sait mener l'exploration de MINIA-09 : demander les operations de Taxo une par une (ARCHITECTURE § 12).
    explores = True

    def __init__(self, model_name, tier=FREE, api_key=None, transport=None, timeout=300.0,
                 num_ctx=DEFAULT_NUM_CTX, sleep=time.sleep):
        if tier not in (FREE, PAID):
            raise ValueError(f'{self.settings_prefix}_TIER invalide : {tier} (free ou paid).')
        if num_ctx < 2 * MAX_OUTPUT_TOKENS:
            raise ValueError(f'{self.settings_prefix}_NUM_CTX trop petit : {num_ctx} (minimum {2 * MAX_OUTPUT_TOKENS}).')
        self.model_name, self.num_ctx = model_name, num_ctx
        # Au niveau gratuit, les donnees envoyees peuvent servir a Mistral ; au niveau payant, non.
        self.data_use = tier == FREE
        self._key, self._sleep = api_key, sleep
        self._client = httpx.Client(timeout=timeout, transport=transport)
        # Un appel qu'on peut arreter a son propre client : l'arret le ferme, meme avant la reponse (TAXO-UX-03).
        self._new_client = lambda: httpx.Client(timeout=timeout, transport=transport)

    def capacity(self, system):
        """Octets disponibles pour le message de l'utilisateur avec ces consignes. Borne sure, comme pour
        Ollama : un texte ne compte jamais plus de tokens que d'octets UTF-8 ; la reponse garde sa place."""
        return self.num_ctx - TEMPLATE_TOKENS - MAX_OUTPUT_TOKENS - len(system.encode('utf-8'))

    def _headers(self):
        key = self._key or os.getenv(self.key_variable, '').strip()
        if not key:
            raise MiniaError(UNAVAILABLE, f'Minia {self.label} n’a pas de clé : définir {self.key_variable}.')
        return {'Authorization': f'Bearer {key}', 'Content-Type': 'application/json', 'Accept': 'application/json'}

    def _format(self, system, schema):
        """Les consignes et la contrainte de la reponse : un schema JSON strict."""
        return system, {'type': 'json_schema', 'json_schema': {'name': 'minia', 'schema': schema, 'strict': True}}

    def _body(self, system, user, stream, schema=None):
        size = len(user.encode('utf-8'))
        if size > self.capacity(system):
            raise MiniaError(CONTEXT_TOO_LARGE, f'La demande dépasse la place réservée à Minia {self.label} ({size} '
                             f'octets pour {max(self.capacity(system), 0)} disponibles) : réduire la sélection ou augmenter '
                             f'{self.settings_prefix}_NUM_CTX.')
        system, response_format = self._format(system, schema or ANSWER_SCHEMA)
        return {'model': self.model_name, 'temperature': 0, self.token_field: MAX_OUTPUT_TOKENS, 'stream': stream,
                'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}],
                'response_format': response_format}

    def _open(self, body, stream, client=None, cancel=None):
        return retrying.send(client or self._client, self.url, body, self._headers(), stream, self._sleep,
                             lambda response: _check(response, self),
                             lambda: _unreachable(self.label), cancel)

    def complete(self, system, user, schema=None, cancel=None):
        """Texte de la reponse, contraint par `schema` (JSON Schema) ; par defaut, la reponse de Minia. Avec
        un jeton d'arret, la reponse passe par le flux, que l'arret coupe (TAXO-UX-03)."""
        if cancel is not None:
            return ''.join(self.stream(system, user, schema, cancel))
        return self._answer(self._open(self._body(system, user, False, schema), stream=False))[0]

    def _answer(self, response):
        """Le texte d'une reponse complete, et le modele qui l'a servie."""
        try:
            data = response.json()
        except ValueError as exc:
            raise MiniaError(UNAVAILABLE, f'Réponse de {self.label} illisible.') from exc
        choice = _choice(data)
        _accepted(choice.get('finish_reason'), self.label)
        return _content((choice.get('message') or {}).get('content')), data.get('model') or self.model_name

    def stream(self, system, user, schema=None, cancel=None):
        """Morceaux de la reponse, au fur et a mesure que Mistral les produit ; rend enfin le modele qui a
        repondu, quand l'API le dit."""
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
                    raise MiniaError(UNAVAILABLE, f'Réponse de {self.label} illisible.') from exc
                served = part.get('model') or served
                choice = _choice(part)
                # Le morceau qui porte une coupure ou une erreur n'est jamais diffuse. Les morceaux deja
                # diffuses ne sont qu'un brouillon provisoire, que le portail efface a l'echec.
                _accepted(choice.get('finish_reason'), self.label)
                text = _content((choice.get('delta') or {}).get('content'))
                if text:
                    yield text
        except (httpx.HTTPError, httpx.StreamError) as exc:
            check(cancel)
            raise _unreachable(self.label) from exc
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


def _accepted(finish, label='Mistral'):
    """Une reponse coupee ou en erreur n'est pas une reponse : Taxo le dit."""
    if finish in _CUT:
        raise MiniaError(UNAVAILABLE, f'La réponse de {label} a été coupée (longueur maximale atteinte).')
    if finish in _FAILED:
        raise MiniaError(UNAVAILABLE, f'{label} n’a pas pu terminer sa réponse : réessayer.')


def _unreachable(label='Mistral'):
    return MiniaError(UNAVAILABLE, f'API {label} injoignable : vérifier la connexion réseau.')


def _message(response):
    try:
        detail = response.json()
    except ValueError:
        return ''
    if not isinstance(detail, dict):
        return ''
    # Mistral dit `message` ou `detail` ; une API compatible OpenAI (Groq) dit `error.message`.
    nested = detail.get('error')
    message = detail.get('message') or detail.get('detail') or (nested.get('message') if isinstance(nested, dict) else '')
    message = message or ''
    return message if isinstance(message, str) else json.dumps(message, ensure_ascii=False)


def _check(response, model):
    """Erreur de l'API du fournisseur, dite en clair."""
    label, message, status = model.label, _message(response), response.status_code
    said = f' {label} : « {message} »' if message else ''
    if status in (401, 403):
        raise MiniaError(UNAVAILABLE, f'Clé {label} refusée : vérifier {model.key_variable}.')
    if status == 404 or (status == 400 and 'model' in message.lower()):
        raise MiniaError(UNAVAILABLE, f'Modèle {label} introuvable ou non accessible avec cette clé : {model.model_name} '
                         f'({model.settings_prefix}_MODEL). Choisir un modèle listé pour ce compte.{said}')
    if status == 413:
        raise MiniaError(UNAVAILABLE, f'Demande trop grande pour la limite de tokens du compte {label} (niveau gratuit '
                         f'très limité) : réduire la sélection ou passer au niveau payant.{said}')
    if status == 429:
        raise MiniaError(UNAVAILABLE, f'Quota de l’API {label} atteint (niveau gratuit limité) : réessayer plus tard.'
                         f'{said}')
    if status == 503:
        raise MiniaError(UNAVAILABLE, f'{label} est momentanément surchargé (503), même après {RETRIES} nouvelles '
                         f'tentatives : réessayer dans un moment, ou choisir un autre modèle.{said}')
    if status in (400, 422):
        raise MiniaError(UNAVAILABLE, f'Requête refusée par l’API {label} : {message or "requête invalide"}')
    raise MiniaError(UNAVAILABLE, f'L’API {label} a répondu {status}.')

