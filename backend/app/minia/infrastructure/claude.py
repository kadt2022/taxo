"""Adaptateur Claude de Minia (API Anthropic, SDK officiel).

Minia Claude fait le meme travail que Minia Ollama : memes consignes, meme contexte borne (faits Taxo et,
sur accord, diff du commit), meme reponse validee par Taxo. Claude est un service distant : tout ce que
Minia recoit quitte la machine de Taxo, d'ou `remote = True`, que le portail signale.

La reponse est contrainte par un schema JSON (sortie structuree) : le modele rend toujours l'objet
{cited, answer, unknown} attendu par Taxo. Les identifiants viennent de l'environnement (ANTHROPIC_API_KEY
ou un profil `ant auth login`), jamais du code.
"""
import anthropic

from app.minia.domain.errors import CONTEXT_TOO_LARGE, UNAVAILABLE, MiniaError

DEFAULT_MODEL = 'claude-opus-5'
MAX_TOKENS = 16000
# La fenetre de Claude est bien plus grande, mais Minia n'en a pas besoin : les limites du contexte (faits,
# diff) restent celles de Taxo. Borne en octets UTF-8, comme pour Ollama (jamais plus de tokens que d'octets).
MAX_INPUT_BYTES = 400_000
# Repli cote serveur si le modele decline une demande (categorie de refus) : un autre modele reprend.
_FALLBACK_BETA = 'server-side-fallback-2026-07-01'
_FALLBACK_MODELS = ('claude-opus-5', 'claude-opus-5-5', 'claude-fable-5-1')

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


class ClaudeModel:
    provider = 'claude'
    remote = True

    def __init__(self, model_name=DEFAULT_MODEL, client=None, max_input_bytes=MAX_INPUT_BYTES):
        self.model_name, self.max_input_bytes = model_name, max_input_bytes
        self._client = client

    def _messages(self):
        # Client cree a la premiere demande : sans identifiants, Taxo demarre quand meme et le dit a l'usage.
        if self._client is None:
            try:
                self._client = anthropic.Anthropic()
            except anthropic.AnthropicError as exc:
                raise _not_configured() from exc
        return self._client.beta.messages

    def capacity(self, system):
        """Octets disponibles pour le message de l'utilisateur avec ces consignes."""
        return self.max_input_bytes - len(system.encode('utf-8'))

    def _request(self, system, user):
        size = len(user.encode('utf-8'))
        if size > self.capacity(system):
            raise MiniaError(CONTEXT_TOO_LARGE, f'La demande dépasse la place réservée à Minia Claude ({size} '
                             f'octets pour {max(self.capacity(system), 0)} disponibles) : réduire la sélection.')
        request = {'model': self.model_name, 'max_tokens': MAX_TOKENS, 'system': system,
                   'messages': [{'role': 'user', 'content': user}],
                   'output_config': {'format': {'type': 'json_schema', 'schema': ANSWER_SCHEMA}}}
        if self.model_name in _FALLBACK_MODELS:
            request.update(betas=[_FALLBACK_BETA], fallbacks='default')
        return request

    def complete(self, system, user):
        request = self._request(system, user)
        try:
            message = self._messages().create(**request)
        except anthropic.AnthropicError as exc:
            raise _failure(exc, self.model_name) from exc
        _accepted(message)
        return ''.join(block.text for block in message.content if block.type == 'text')

    def stream(self, system, user):
        """Morceaux de la reponse, au fur et a mesure que Claude les produit."""
        request = self._request(system, user)
        try:
            with self._messages().stream(**request) as stream:
                yield from stream.text_stream
                _accepted(stream.get_final_message())
        except anthropic.AnthropicError as exc:
            raise _failure(exc, self.model_name) from exc


def _accepted(message):
    """Une reponse refusee ou coupee n'est pas une reponse : Taxo le dit plutot que d'afficher un morceau."""
    if message.stop_reason == 'refusal':
        raise MiniaError(UNAVAILABLE, 'Claude a décliné cette demande : reformuler la question.')
    if message.stop_reason == 'max_tokens':
        raise MiniaError(UNAVAILABLE, 'La réponse de Claude a été coupée (longueur maximale atteinte).')


def _not_configured():
    return MiniaError(UNAVAILABLE, 'Minia Claude n’a pas d’identifiants : définir ANTHROPIC_API_KEY.')


def _failure(exc, model_name):
    """Erreur de l'API Claude, dite en clair ; les plus precises d'abord."""
    if isinstance(exc, anthropic.CredentialsError):
        return _not_configured()
    if isinstance(exc, anthropic.AuthenticationError):
        return MiniaError(UNAVAILABLE, 'Clé Claude refusée : vérifier ANTHROPIC_API_KEY.')
    if isinstance(exc, anthropic.PermissionDeniedError):
        return MiniaError(UNAVAILABLE, 'Le compte Claude n’a pas accès à ce modèle ou à cette fonction.')
    if isinstance(exc, anthropic.NotFoundError):
        return MiniaError(UNAVAILABLE, f'Modèle Claude inconnu : {model_name} (MINIA_CLAUDE_MODEL).')
    if isinstance(exc, anthropic.RateLimitError):
        return MiniaError(UNAVAILABLE, 'Limite de débit de l’API Claude atteinte : réessayer dans un moment.')
    if isinstance(exc, anthropic.BadRequestError):
        return MiniaError(UNAVAILABLE, f'Requête refusée par l’API Claude : {exc.message}')
    if isinstance(exc, anthropic.APIStatusError):
        return MiniaError(UNAVAILABLE, f'L’API Claude a répondu {exc.status_code}.')
    if isinstance(exc, anthropic.APIConnectionError):
        return MiniaError(UNAVAILABLE, 'API Claude injoignable : vérifier la connexion réseau.')
    return MiniaError(UNAVAILABLE, f'Erreur de l’API Claude : {exc}')
