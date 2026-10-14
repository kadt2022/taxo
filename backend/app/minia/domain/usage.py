"""Ce que coûte une demande à Minia, tel que le fournisseur le rapporte (récit TAXO-RECIT-REDUCTION-PAYLOAD-MINIA, R0).

Une mesure, jamais un fait : rien n'est stocké, rien n'est montré comme une preuve. Trois volumes à ne pas confondre :

- **Taxo → Minia** : les octets des réponses de Taxo (la trajectoire), ventilés entre l'exploration et les
  vérifications que Minia lance après la conclusion du modèle (celles-ci ne sont jamais renvoyées au modèle) ;
- **Minia → modèle** : les octets réellement envoyés à chaque appel (consignes et message, après protection) ;
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
"""
KEYS = ('input', 'cache_read', 'cache_write', 'output', 'reasoning')
# Ce que `input` compte, selon le fournisseur : l'entrée hors cache (Claude) ou toute l'entrée (Gemini).
INPUT_EXCLUDES_CACHE = {'claude': True, 'claude-sonnet': True, 'gemini': False, 'gemini-lite': False}


def _count(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def counters(**values):
    """Les compteurs normalisés ; une valeur absente ou invalide est « non rapportée »."""
    return {key: _count(values.get(key)) for key in KEYS}


def claude(usage):
    """Les compteurs de l'objet `usage` d'une réponse Claude."""
    if usage is None:
        return counters()
    read = lambda name: getattr(usage, name, None)
    return counters(input=read('input_tokens'), cache_read=read('cache_read_input_tokens'),
                    cache_write=read('cache_creation_input_tokens'), output=read('output_tokens'))


def gemini(metadata):
    """Les compteurs du champ `usageMetadata` d'une réponse Gemini."""
    if not isinstance(metadata, dict):
        return counters()
    return counters(input=metadata.get('promptTokenCount'), cache_read=metadata.get('cachedContentTokenCount'),
                    output=metadata.get('candidatesTokenCount'), reasoning=metadata.get('thoughtsTokenCount'))


def _size(text):
    return len(text.encode('utf-8')) if isinstance(text, str) else 0


class Ledger:
    """Le relevé d'une demande : un appel au modèle par ligne. Vit le temps de la demande, en mémoire."""

    def __init__(self):
        self.calls = []

    def record(self, model, system, message, reported=None, failed=False):
        call = {'provider': getattr(model, 'provider', None), 'model': getattr(model, 'model_name', None),
                'system_bytes': _size(system), 'message_bytes': _size(message), **(reported or counters())}
        if failed:
            call['failed'] = True
        self.calls.append(call)
        return call

    def report(self, trajectory=None, verification_from=None):
        """Le relevé de la demande. `verification_from` : l'indice de la trajectoire où commencent les vérifications
        lancées par Minia après la conclusion (elles ne sont pas renvoyées au modèle)."""
        totals, unreported = {}, {}
        for key in KEYS:
            values = [call[key] for call in self.calls]
            missing = sum(1 for value in values if value is None)
            totals[key] = sum(values) if values and not missing else None
            if missing:
                unreported[key] = missing
        steps = list(trajectory or [])
        cut = len(steps) if verification_from is None else verification_from
        taxo_bytes = lambda items: sum(item.get('bytes') or 0 for item in items)
        providers = sorted({call['provider'] for call in self.calls if call['provider']})
        return {
            'calls': len(self.calls),
            'sent_bytes': sum(call['system_bytes'] + call['message_bytes'] for call in self.calls),
            'taxo_bytes': {'exploration': taxo_bytes(steps[:cut]), 'verification': taxo_bytes(steps[cut:])},
            'tokens': totals,
            'unreported': unreported,
            'input_excludes_cache': {name: INPUT_EXCLUDES_CACHE.get(name) for name in providers},
            'per_call': [dict(call) for call in self.calls],
        }
