"""Ce que coûte une demande à Minia, tel que le fournisseur le rapporte (récit TAXO-RECIT-REDUCTION-PAYLOAD-MINIA, R0).

Une mesure, jamais un fait : rien n'est stocké, rien n'est montré comme une preuve. Trois volumes à ne pas confondre :

- **Taxo → Minia** : les octets des réponses de Taxo (la trajectoire), ventilés entre l'exploration et les
  vérifications que Minia lance après la conclusion du modèle (celles-ci ne sont jamais renvoyées au modèle) ;
- **Minia → modèle** : `prompt_bytes`, la taille UTF-8 des consignes et du message de chaque appel, après
  protection. Ce n'est pas la taille de la requête HTTP : l'enveloppe JSON, le schéma de réponse et les en-têtes n'y
  sont pas ;
- **usage du fournisseur** : les compteurs que son API rapporte, appel par appel.

Compteurs, dans les catégories du fournisseur (aucun découpage inventé) :

| Clé | Claude (`usage`) | Gemini (`usageMetadata`) |
|---|---|---|
| `input` | `input_tokens` : entrée hors cache | `promptTokenCount` : toute l'entrée, cache compris |
| `cache_read` | `cache_read_input_tokens` | `cachedContentTokenCount` (inclus dans `input`) |
| `cache_write` | `cache_creation_input_tokens` | non rapporté |
| `output` | `output_tokens` (réflexion comprise) | `candidatesTokenCount` |
| `reasoning` | non rapporté (inclus dans `output`) | `thoughtsTokenCount` |

Ces compteurs sont **observés**, jamais provoqués : relever les jetons qu'un fournisseur met en cache de lui-même ne
demande, n'active ni ne configure aucun cache. Un compteur absent vaut `None` (« non rapporté »), jamais zéro ; un total
n'est donné que si tous les appels l'ont rapporté.

Les totaux sont **par modèle**, celui qui a réellement répondu (un repli côté serveur peut en changer) : des tokens de
modèles différents ne s'additionnent pas. Un appel en erreur sans compteur rapporté (rejeté avant l'envoi, ou échoué
en route : Minia ne le sait pas toujours) est compté à part (`failed_calls`), hors des totaux ; un appel refusé ou coupé
dont le fournisseur rapporte l'usage reste compté, puisqu'il est facturé.
"""
KEYS = ('input', 'cache_read', 'cache_write', 'output', 'reasoning')
# Ce que `input` compte, selon le fournisseur : l'entrée hors cache (Claude) ou toute l'entrée (Gemini).
INPUT_EXCLUDES_CACHE = {'claude': True, 'claude-sonnet': True, 'gemini': False, 'gemini-lite': False}


def _count(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def counters(**values):
    """Les compteurs normalisés ; une valeur absente ou invalide est « non rapportée »."""
    return {key: _count(values.get(key)) for key in KEYS}


def _served(found, served):
    return {**found, 'served': served} if isinstance(served, str) and served else found


def claude(usage, served=None):
    """Les compteurs de l'objet `usage` d'une réponse Claude, et le modèle qui a réellement répondu."""
    if usage is None:
        return _served(counters(), served)
    read = lambda name: getattr(usage, name, None)
    return _served(counters(input=read('input_tokens'), cache_read=read('cache_read_input_tokens'),
                            cache_write=read('cache_creation_input_tokens'), output=read('output_tokens')), served)


def gemini(metadata, served=None):
    """Les compteurs du champ `usageMetadata` d'une réponse Gemini, et la version qui a répondu."""
    if not isinstance(metadata, dict):
        return _served(counters(), served)
    return _served(counters(input=metadata.get('promptTokenCount'), cache_read=metadata.get('cachedContentTokenCount'),
                            output=metadata.get('candidatesTokenCount'),
                            reasoning=metadata.get('thoughtsTokenCount')), served)


def _size(text):
    return len(text.encode('utf-8')) if isinstance(text, str) else 0


class Ledger:
    """Le relevé d'une demande : un appel au modèle par ligne. Vit le temps de la demande, en mémoire."""

    def __init__(self):
        self.calls = []

    def record(self, model, system, message, reported=None, failed=False):
        reported = dict(reported or {})
        served = reported.pop('served', None)
        call = {'provider': getattr(model, 'provider', None),
                'model': served or getattr(model, 'model_name', None),
                'system_bytes': _size(system), 'message_bytes': _size(message), **counters(**reported)}
        if failed:
            call['failed'] = True
        self.calls.append(call)
        return call

    @staticmethod
    def _counted(call):
        """Un appel compte s'il a abouti, ou si le fournisseur en a rapporté l'usage (refus ou coupure facturés)."""
        return not call.get('failed') or any(call[key] is not None for key in KEYS)

    def report(self, trajectory=None, verification_from=None):
        """Le relevé de la demande. `verification_from` : l'indice de la trajectoire où commencent les vérifications
        lancées par Minia après la conclusion (elles ne sont pas renvoyées au modèle)."""
        counted = [call for call in self.calls if self._counted(call)]
        by_model = {}
        for call in counted:
            by_model.setdefault(f'{call["provider"]}/{call["model"]}', []).append(call)
        steps = list(trajectory or [])
        cut = len(steps) if verification_from is None else verification_from
        taxo_bytes = lambda items: sum(item.get('bytes') or 0 for item in items)
        return {
            'calls': len(counted),
            'failed_calls': len(self.calls) - len(counted),
            'prompt_bytes': sum(call['system_bytes'] + call['message_bytes'] for call in counted),
            'taxo_bytes': {'exploration': taxo_bytes(steps[:cut]), 'verification': taxo_bytes(steps[cut:])},
            'by_model': {name: _totals(calls) for name, calls in sorted(by_model.items())},
            'per_call': [dict(call) for call in self.calls],
        }


def _totals(calls):
    """Les tokens d'un même modèle ; un total seulement si chaque appel l'a rapporté."""
    tokens, unreported = {}, {}
    for key in KEYS:
        values = [call[key] for call in calls]
        missing = sum(1 for value in values if value is None)
        tokens[key] = sum(values) if not missing else None
        if missing:
            unreported[key] = missing
    provider = calls[0]['provider']
    return {'calls': len(calls), 'tokens': tokens, 'unreported': unreported,
            'input_excludes_cache': INPUT_EXCLUDES_CACHE.get(provider)}
