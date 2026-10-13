"""`get_source` : le code d'un symbole déclaré, lu à la demande sous son propre consentement (TAXO-MIP-ADT-01, PR B ;
ARCHITECTURE § 12.6).

La demande nomme une référence de symbole, jamais un chemin : le fichier et les lignes viennent de la preuve de sa
déclaration dans la Maille, au commit de l'analyse. Le code n'est transmis que si tout concorde :

1. une seule déclaration écrite (`CONTAINS` observé) du symbole, par un analyseur qui sait en lire la plage ;
2. l'analyse de l'échange porte sur un commit (jamais sur le dossier de travail), et la preuve vient de ce commit ;
3. le fichier se lit à ce commit sans refus (confidentiel, généré, binaire, lien, trop gros) ;
4. les lignes de la preuve ont toujours la même empreinte ;
5. l'analyseur retrouve la déclaration, à la ligne de la preuve, une seule fois (une surcharge par sa signature).

Sinon, la réponse dit pourquoi rien n'est transmis (`not_sent`), et sa classification n'annonce aucun code. Rien de ce
qui est lu n'est conservé. Le protocole ne connaît aucun langage : la plage vient de l'analyseur.
"""
import json

from app.facts import content_hash
from app.history.domain.disclosure import GENERATED, generated
from app.protocol.application.arguments import no_other, reference as _reference
from app.protocol.domain import source
from app.protocol.domain.envelope import BUDGET_EXHAUSTED, INVALID_ARGUMENT, NO_CONSENT, NOT_AVAILABLE, OperationError

_DECLARES = 'CONTAINS'
_CALLS, _TYPED_AS = 'CALLS', 'TYPED_AS'
_SYMBOL = 'symbol:'
_WHAT = 'source'


class SourceOperation:
    """`get_source` pour un échange : ses faits, son historique et les lecteurs de plage des analyseurs."""

    def __init__(self, exchange, history, readers):
        self.exchange, self.history, self.readers = exchange, history, readers

    def get_source(self, arguments, max_bytes):
        no_other(arguments, ('reference',))
        if not self.exchange.source_consent:
            raise OperationError(NO_CONSENT, 'La lecture du code n’a pas été autorisée pour cet échange.')
        reference = _reference(arguments, 'reference', required=True)
        if not reference.startswith(_SYMBOL):
            raise OperationError(INVALID_ARGUMENT, 'reference : un symbole (type, méthode ou constructeur), jamais '
                                                   'un fichier ni un chemin.')
        if source.nature(reference) == 'MEMBER':
            raise OperationError(INVALID_ARGUMENT, 'reference : un type, une méthode ou un constructeur ; un champ '
                                                   'n’a pas de code propre.')
        self.exchange.own(reference)
        if not self.exchange.committed:
            # Le commit n'est pas ce que l'analyse du dossier de travail a lu : son code serait celui d'un autre état.
            raise OperationError(NOT_AVAILABLE, 'Le code n’est lu que pour l’analyse d’un commit, jamais pour celle '
                                                'du dossier de travail.')
        proof, producer = self._declaration(reference)
        commit = self.exchange.snapshot['commit']
        path = proof['path']
        found, reason, fields = self._read(reference, proof, producer)
        # Le contexte des champs n'accompagne qu'une méthode ou un constructeur servis : sa section, sa portée.
        context = ({source.FIELD_CONTEXT: [], 'field_context_scope': source.FIELD_CONTEXT_SCOPE,
                    source.USES: [], 'uses_scope': source.USES_SCOPE}
                   if found is not None and source.nature(reference) == 'METHOD' else {})
        response = self.exchange.response(
            'get_source', self.exchange.envelope_coverage(_DECLARES, {reference}), max_bytes, reference=reference,
            commit=commit, path=path,
            classification=source.classify(reference, self.exchange.snapshot, path, producer, found is not None),
            disclosure=source.disclosure(found is not None), **context)
        if found is None:
            response.not_sent({'what': _WHAT, 'reason': reason})
            return response
        item = {'kind': _WHAT, 'reference': reference, 'path': path, 'line_start': found.line_start,
                'line_end': found.line_end, 'truncated': found.truncated,
                'declared': {'line_start': found.line_start, 'line_end': found.declared_end},
                'content_hash': found.content_hash, 'declaration_hash': proof['content_hash'], 'text': found.text}
        if not response.add('items', item):
            # Une classification qui annoncerait un code absent serait fausse : la réponse n'est pas servie.
            raise OperationError(BUDGET_EXHAUSTED, 'Cette pièce source ne tient pas dans le budget : augmenter '
                                                   'max_bytes.')
        if context:
            _field_context(response, reference, fields)
            self._uses(response, reference, fields)
        return response

    def _uses(self, response, reference, fields):
        """Les références où mène la méthode, établies par la Maille : ses appels, puis le type de ses champs."""
        owner = reference.split('#', 1)[0]
        found = [{'relation': _CALLS, 'reference': fact['object']} for fact in self._facts(reference, _CALLS)]
        for name, _ in fields:
            field = f'{owner}#{name}'
            found += [{'relation': _TYPED_AS, 'from': field, 'reference': fact['object']}
                      for fact in self._facts(field, _TYPED_AS)]
        unique = list({(item['relation'], item.get('from'), item['reference']): item for item in found}.values())
        for item in unique[:source.MAX_USES]:
            if not response.add(source.USES, item):
                break
        if len(unique) > source.MAX_USES:
            response.not_sent({'what': source.USES, 'count': len(unique) - source.MAX_USES, 'reason': source.LIMIT})

    def _facts(self, subject, relation):
        """Les faits valides de la Maille pour ce sujet et cette relation, dans l'ordre de leur objet."""
        return sorted((fact for fact in self.exchange.query(subject=subject, relation=relation, kind='ASSERTION')
                       if fact.get('validity', 'VALID') == 'VALID' and fact.get('object')),
                      key=lambda fact: fact['object'])

    def _declaration(self, reference):
        """La preuve de l'unique déclaration écrite du symbole, et l'analyseur qui l'a produite."""
        located = {}
        for fact in self.exchange.query(relation=_DECLARES, object=reference, kind='ASSERTION'):
            producer = fact.get('produced_by', {}).get('producer_id')
            written = fact.get('status') == 'OBSERVED' and fact.get('validity', 'VALID') == 'VALID'
            if not written or producer not in self.readers:
                continue
            for proof in fact.get('evidence', []):
                if proof.get('symbol') == reference and proof.get('content_hash'):
                    key = (proof['path'], proof['line_start'], proof['line_end'], proof['content_hash'],
                           proof.get('commit'))
                    located.setdefault(key, (proof, producer))
        if not located:
            raise OperationError(NOT_AVAILABLE, 'Aucune déclaration écrite de ce symbole dans cette analyse.')
        if len(located) > 1:
            raise OperationError(NOT_AVAILABLE, 'Ce symbole est déclaré à plusieurs endroits : sa lecture serait '
                                                'ambiguë.')
        proof, producer = next(iter(located.values()))
        commit = self.exchange.snapshot['commit']
        if commit is None or proof.get('commit') != commit:
            raise OperationError(NOT_AVAILABLE, 'La preuve de cette déclaration ne vient pas du commit de l’analyse.')
        return proof, producer

    def _read(self, reference, proof, producer):
        """La pièce source, ou None et la raison de ne pas la transmettre ; et les pièces des champs qu'elle utilise."""
        path = proof['path']
        if generated(path):
            return None, GENERATED, ()
        content, reason = self.history.source(self.exchange.project_id, proof['commit'], path)
        if content is None:
            return None, reason, ()
        try:
            unchanged = content_hash(content, proof['line_start'], proof['line_end']) == proof['content_hash']
        except ValueError:
            unchanged = False
        if not unchanged:
            return None, source.CHANGED, ()
        lines = self.readers[producer](path, content, reference)
        if lines is None or lines.name_line != proof['line_start']:
            return None, source.NOT_DECLARED, ()
        found = source.piece(content, lines.line_start, lines.line_end)
        if found is None:
            return None, source.LIMIT, ()
        # Un champ n'est joint que si sa déclaration se lit en entier : une déclaration partielle reste None, comptée.
        fields = ((item.name, source.piece(content, item.line_start, item.line_end))
                  for item in getattr(lines, 'fields', ()))
        return found, None, tuple((name, piece if piece is not None and not piece.truncated else None)
                                  for name, piece in fields)


def _field_context(response, reference, fields):
    """Les déclarations des champs utilisés, dans leur section et sous leur plafond ; le reste est compté. Un champ
    est lu dans le fichier de la pièce (`path` de la réponse) : il ne le répète pas."""
    owner, used, refused = reference.split('#', 1)[0], 0, 0
    partial = sum(1 for _, piece in fields if piece is None)
    for name, piece in fields:
        if piece is None:
            continue
        item = {'field': f'{owner}#{name}', 'line_start': piece.line_start, 'line_end': piece.line_end,
                'content_hash': piece.content_hash, 'resolution': source.RESOLVED, 'text': piece.text}
        cost = len(json.dumps(item, ensure_ascii=False).encode('utf-8'))
        if refused or used + cost > source.MAX_FIELD_CONTEXT_BYTES:
            refused += 1
            continue
        if not response.add(source.FIELD_CONTEXT, item):
            continue
        used += cost
    if partial:
        # Une déclaration plus longue que les limites d'une pièce n'est jamais jointe coupée, ni tue.
        response.not_sent({'what': source.FIELD_CONTEXT, 'count': partial, 'reason': source.LIMIT})
    if refused:
        response.not_sent({'what': source.FIELD_CONTEXT, 'count': refused, 'reason': source.FIELD_CONTEXT_LIMIT})
