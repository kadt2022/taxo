"""Adaptateur Ollama de Minia.

Le modele recoit la projection Taxo de MINIA-01 (faits changes, localisation des preuves, couverture,
metadonnees du commit) et, seulement si MINIA_SOURCE_CONTEXT=diff et que la demande l'autorise, le diff
du commit (ADR 0008). MINIA_OLLAMA_URL peut viser un Ollama local ou distant : s'il est distant, ces
donnees quittent le processus et la machine de Taxo ; `remote` le signale au portail.
"""
import ipaddress
import json
from urllib.parse import urlsplit

import httpx

from app.minia.domain.errors import CONTEXT_TOO_LARGE, UNAVAILABLE, MiniaError

DEFAULT_URL = 'http://127.0.0.1:11434'
DEFAULT_NUM_CTX = 16384
# Borne sure, sans tokeniseur : les modeles servis (Qwen, Llama...) utilisent un BPE au niveau de l'octet,
# ou chaque token porte au moins un octet ; un texte ne compte donc jamais plus de tokens que d'octets UTF-8,
# quelle que soit sa langue. S'y ajoutent le gabarit de conversation et une part reservee a la reponse.
TEMPLATE_TOKENS = 64
ANSWER_TOKENS = 1024


def _loopback(host):
    """Vrai si l'adresse designe cette machine : ce qui y est envoye ne la quitte pas."""
    if host.lower() == 'localhost':
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class OllamaModel:
    provider = 'ollama'

    def __init__(self, model_name, url=DEFAULT_URL, timeout=300.0, transport=None, num_ctx=DEFAULT_NUM_CTX):
        parts = urlsplit(url)
        if parts.scheme not in {'http', 'https'} or not parts.hostname:
            raise ValueError(f'MINIA_OLLAMA_URL invalide : {url}')
        if num_ctx < 2 * ANSWER_TOKENS:
            raise ValueError(f'MINIA_OLLAMA_NUM_CTX trop petit : {num_ctx} (minimum {2 * ANSWER_TOKENS}).')
        self.model_name, self.url, self.num_ctx = model_name, url.rstrip('/'), num_ctx
        self.remote = not _loopback(parts.hostname)
        self._client = httpx.Client(timeout=timeout, transport=transport)

    def capacity(self, system):
        """Octets disponibles pour le message de l'utilisateur avec ces consignes : Minia y ajuste son contexte."""
        return self.num_ctx - TEMPLATE_TOKENS - ANSWER_TOKENS - len(system.encode('utf-8'))

    def _body(self, system, user, stream):
        """Requete a Ollama, avec une fenetre de contexte explicite.

        Sans `num_ctx`, Ollama garde sa fenetre par defaut (2 048 ou 4 096 tokens) et tronque en silence le
        debut d'un message trop long, c'est-a-dire les consignes : le modele repond alors sans connaitre le
        format attendu, ni les regles qui lui interdisent de suivre des instructions venues du code. Un
        message qui pourrait ne pas tenir est refuse plutot que tronque.
        """
        size = len(user.encode('utf-8'))
        if size > self.capacity(system):
            raise MiniaError(CONTEXT_TOO_LARGE, f'La demande dépasse la fenêtre de Minia ({size} octets pour '
                             f'{max(self.capacity(system), 0)} disponibles) : réduire la sélection ou augmenter '
                             'MINIA_OLLAMA_NUM_CTX.')
        return {'model': self.model_name, 'stream': stream, 'format': 'json',
                'options': {'temperature': 0, 'num_ctx': self.num_ctx},
                'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}]}

    def _check(self, response):
        if response.status_code == 404:
            raise MiniaError(UNAVAILABLE, f'Modèle absent d’Ollama : lancer « ollama pull {self.model_name} ».')
        if response.status_code != 200:
            raise MiniaError(UNAVAILABLE, f'Ollama a répondu {response.status_code}.')

    def _unreachable(self, exc):
        return MiniaError(UNAVAILABLE, f'Ollama est injoignable à {self.url} : lancer « ollama serve ».')

    def complete(self, system, user):
        try:
            response = self._client.post(f'{self.url}/api/chat', json=self._body(system, user, False))
        except httpx.HTTPError as exc:
            raise self._unreachable(exc) from exc
        self._check(response)
        try:
            return response.json()['message']['content']
        except (ValueError, KeyError, TypeError) as exc:
            raise MiniaError(UNAVAILABLE, 'Réponse d’Ollama illisible.') from exc

    def stream(self, system, user):
        """Morceaux de la reponse, au fur et a mesure qu'Ollama les produit (une ligne JSON par morceau)."""
        try:
            with self._client.stream('POST', f'{self.url}/api/chat', json=self._body(system, user, True)) as response:
                self._check(response)
                for line in response.iter_lines():
                    if not line.strip():
                        continue
                    try:
                        part = json.loads(line)
                        chunk = part.get('message', {}).get('content', '')
                    except (ValueError, AttributeError) as exc:
                        raise MiniaError(UNAVAILABLE, 'Réponse d’Ollama illisible.') from exc
                    if chunk:
                        yield chunk
                    if part.get('done'):
                        return
        except httpx.HTTPError as exc:
            raise self._unreachable(exc) from exc
