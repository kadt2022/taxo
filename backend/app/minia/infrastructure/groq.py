"""Adaptateur Groq de Minia (GroqCloud, API compatible OpenAI, REST).

Minia Groq fait le meme travail que les autres fournisseurs : memes consignes, meme contexte borne, meme reponse
validee par Taxo, et le mode exploration (ARCHITECTURE § 12). Il reprend l'adaptateur de Mistral (meme famille d'API)
et n'en change que ses constantes et la contrainte de la reponse. Groq est un service distant (`remote = True`) : ce que
Minia recoit quitte la machine de Taxo. Groq dit ne conserver aucune donnee d'inference par defaut, mais sa page ne
dit pas si les donnees servent a entrainer des modeles : au niveau gratuit, Taxo le suppose (`data_use = True`, comme
Mistral et Gemini), le portail le dit et le diff reste decoche par defaut.

La reponse est contrainte par un schema JSON strict pour les modeles que Groq documente ; pour les autres, par un
objet JSON dont le schema est redit dans les consignes. Groq ne gere pas le flux avec le schema strict : ces modeles
repondent en une fois (la reponse arrive d'un bloc, l'arret ferme toujours la connexion). La cle vient de
l'environnement (GROQ_API_KEY), jamais du code ni du depot.
"""
import json

from app.minia.infrastructure.calls import client_for
from app.minia.infrastructure.mistral import MistralModel

API_URL = 'https://api.groq.com/openai/v1/chat/completions'
# Les modeles qui gerent le schema strict (documentation de Groq) ; les autres ne garantissent que du JSON valide.
STRICT_MODELS = frozenset({'openai/gpt-oss-20b', 'openai/gpt-oss-120b', 'qwen/qwen3.8-27b'})
_SCHEMA_NOTE = '\n\nReponds par un seul objet JSON conforme a ce schema JSON :\n{}'


class GroqModel(MistralModel):
    provider = 'groq'
    label = 'Groq'
    url = API_URL
    key_variable = 'GROQ_API_KEY'
    settings_prefix = 'MINIA_GROQ'
    token_field = 'max_completion_tokens'

    def _format(self, system, schema):
        """Schema strict pour les modeles qui le gerent ; sinon un objet JSON, avec le schema dans les consignes."""
        if self.model_name in STRICT_MODELS:
            return super()._format(system, schema)
        return system + _SCHEMA_NOTE.format(json.dumps(schema, ensure_ascii=False)), {'type': 'json_object'}

    def stream(self, system, user, schema=None, cancel=None):
        """Les morceaux de la reponse. Avec le schema strict, Groq ne gere pas le flux : la reponse est demandee en
        une fois (la connexion reste arretable) et rendue d'un bloc."""
        if self.model_name not in STRICT_MODELS:
            return (yield from super().stream(system, user, schema, cancel))
        body = self._body(system, user, False, schema)
        with client_for(self._client, self._new_client, cancel) as client:
            text, served = self._answer(self._open(body, False, client, cancel))
        if text:
            yield text
        return served
