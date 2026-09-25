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

from app.minia.domain.errors import UNAVAILABLE, MiniaError

DEFAULT_URL = 'http://127.0.0.1:11434'


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

    def __init__(self, model_name, url=DEFAULT_URL, timeout=300.0, transport=None):
        parts = urlsplit(url)
        if parts.scheme not in {'http', 'https'} or not parts.hostname:
            raise ValueError(f'MINIA_OLLAMA_URL invalide : {url}')
        self.model_name, self.url = model_name, url.rstrip('/')
        self.remote = not _loopback(parts.hostname)
        self._client = httpx.Client(timeout=timeout, transport=transport)

    def _body(self, system, user, stream):
        return {'model': self.model_name, 'stream': stream, 'format': 'json', 'options': {'temperature': 0},
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
