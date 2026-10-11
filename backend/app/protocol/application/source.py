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
from app.facts import content_hash
from app.history.domain.disclosure import GENERATED, generated
from app.protocol.application.arguments import no_other, reference as _reference
from app.protocol.domain import source
from app.protocol.domain.envelope import BUDGET_EXHAUSTED, INVALID_ARGUMENT, NO_CONSENT, NOT_AVAILABLE, OperationError

_DECLARES = 'CONTAINS'
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
        found, reason = self._read(reference, proof, producer)
        response = self.exchange.response(
            'get_source', self.exchange.envelope_coverage(_DECLARES, {reference}), max_bytes, reference=reference,
            commit=commit, path=path,
            classification=source.classify(reference, self.exchange.snapshot, path, producer, found is not None),
            disclosure=source.disclosure(found is not None))
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
        return response

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
        """La pièce source, ou None et la raison de ne pas la transmettre."""
        path = proof['path']
        if generated(path):
            return None, GENERATED
        content, reason = self.history.source(self.exchange.project_id, proof['commit'], path)
        if content is None:
            return None, reason
        try:
            unchanged = content_hash(content, proof['line_start'], proof['line_end']) == proof['content_hash']
        except ValueError:
            unchanged = False
        if not unchanged:
            return None, source.CHANGED
        lines = self.readers[producer](path, content, reference)
        if lines is None or lines.name_line != proof['line_start']:
            return None, source.NOT_DECLARED
        found = source.piece(content, lines.line_start, lines.line_end)
        return (found, None) if found is not None else (None, source.LIMIT)
