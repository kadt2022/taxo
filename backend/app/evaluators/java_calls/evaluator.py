"""Evaluateur des appels Java (TAXO-01K, ARCHITECTURE § 14) : les declarations des sources et les appels
statiquement etablis entre elles, en faits.

Il est generique Java : il ne connait ni controleur, ni service, ni repository, ni Spring. Il produit :

- les declarations ecrites (`OBSERVED`) : un fichier `CONTAINS` ses types, un type `CONTAINS` ses types membres,
  methodes, constructeurs et champs (les composants d'un record sont ses champs) ; un champ `TYPED_AS` son type
  declare quand c'est un type des sources ; un type `EXTENDS` ou `IMPLEMENTS` ses supertypes des sources ; une
  methode `CONTAINS` le parametre ou la variable locale receveur d'un appel etabli, qui `TYPED_AS` son type declare
  (TAXO-01L) ;
- les appels (`INFERRED`) : `CALLS` d'une methode ou d'un constructeur vers la declaration que la regle
  `java.calls.declared-receiver-unique-target/4` etablit, ses premisses etant les declarations ci-dessus ;
- les accesseurs implicites des records (`INFERRED`) : un record `CONTAINS` l'accesseur `x()` de chaque composant
  que son corps n'ecrit pas (`java.record.implicit-accessor/1`, TAXO-01L) ;
- les implementations de methodes (`INFERRED`) : `IMPLEMENTS` d'une methode vers la methode de meme signature
  d'une interface que sa classe implemente (`java.implements.same-signature/1`).

Chaque site qu'il ne resout pas est decrit, avec sa raison fermee, dans le diagnostic d'une couverture
`NOT_INTERPRETED` de la methode qui le porte : jamais une cible inventee. `DISPATCHES_TO` n'est jamais produit.
"""
from collections import Counter

from app.evaluations.domain.evaluator import EvaluationOutput
from app.evaluations.domain.progress import silent
from app.evaluations.domain.status import EvaluationStatus
from app.evaluators.java import sites, sources
from . import accessors, classification, implementations
from .catalog import CATALOG
from .declarations import Sources, supertype_relation, symbol
from .facts import Facts, coverage, site_diagnostic, site_order
from .resolution import Resolver

PARSE_ERROR_REASON = 'Fichier Java lu en partie (erreur de syntaxe) : ses déclarations et ses appels ne sont pas lus.'


class JavaCallsEvaluator:
    evaluator_id = 'taxo.java-calls'
    producer_version = '1.4.0'
    catalog = CATALOG

    def evaluate(self, snapshot, progress=silent):
        repository = f'repository:{snapshot.repository}'
        selected, excluded = sources.select(snapshot)
        warnings, read_errors = [], []
        contents = sources.read(snapshot, selected, warnings, read_errors, progress)
        parsed = sources.parse_all(contents)
        run = _Run(snapshot, contents, Sources(parsed))
        for java_file in parsed:
            run.read(java_file)
        for found in implementations.of(run.index):
            run.facts.implementation(found)
        progress('calls', 'Appels Java établis', run.resolved)
        readable = [java_file for java_file in parsed if not java_file.has_errors]
        warnings += [f'Fichier Java lu en partie (erreur de syntaxe) : {java_file.path}'
                     for java_file in parsed if java_file.has_errors]
        found = [coverage(repository, 'ANALYSED', repository, exclude=excluded)]
        found += [coverage(f'file:{java_file.path}', 'ANALYSED', f'file:{java_file.path}') for java_file in readable]
        found += run.gaps()
        found += [coverage(subject, 'READ_ERROR', subject) for subject in read_errors]
        partial = read_errors or len(readable) < len(parsed)
        status = EvaluationStatus.PARTIAL if partial else EvaluationStatus.SUCCESS
        legacy = {'java_files': len(contents), 'call_sites': run.seen, 'resolved_sites': run.resolved,
                  'not_interpreted': dict(sorted(run.reasons.items()))}
        return EvaluationOutput(run.facts.assertions(), tuple(found), status, tuple(warnings), legacy)


class _Run:
    """Une execution : les faits etablis et, par methode proprietaire, les sites non interpretes."""

    def __init__(self, snapshot, contents, index):
        self.index, self.resolver = index, Resolver(index)
        self.facts = Facts(snapshot, contents)
        self._unread, self._notes = {}, {}
        self.seen = self.resolved = 0
        self.reasons = Counter()

    def read(self, java_file):
        if java_file.has_errors:
            self._note(f'file:{java_file.path}', java_file.path, PARSE_ERROR_REASON)
            return
        for java_type in java_file.types:
            self._declare(java_file, java_type)
        for site in sites.of(java_file):
            self._site(java_file, site)

    def gaps(self):
        """Une couverture `NOT_INTERPRETED` par proprietaire : ses sites non interpretes, tries par position et
        classes (TAXO-01M), et ce qu'il faut en dire."""
        found = []
        for key in sorted(set(self._unread) | set(self._notes)):
            subject, path = key
            listed, notes = sorted(self._unread.get(key, []), key=site_order), self._notes.get(key, [])
            reasons = sorted({item['reason'] for item in listed})
            said = notes + ([f'{len(listed)} appel(s) non interprété(s) : {", ".join(reasons)}'] if listed else [])
            diagnostic = ({'sites_seen': len(listed), 'classification': classification.RULE, 'sites': listed}
                          if listed else None)
            found.append(coverage(subject, 'NOT_INTERPRETED', f'file:{path}', ' ; '.join(said), diagnostic))
        return found

    def _declare(self, java_file, java_type):
        qualified, path = java_type.qualified_name, java_file.path
        outer = qualified.rpartition('.')[0]
        holder = symbol(outer) if self.index.get(outer) is not None and outer != java_file.package else f'file:{path}'
        self.facts.declaration(holder, 'CONTAINS', symbol(qualified), path, java_type.name_line)
        if qualified in self.index.duplicated:
            self._note(symbol(qualified), path, f'Type déclaré plusieurs fois dans les sources : {qualified}')
            return
        for member in java_type.declarations:
            if java_type.ambiguous(member.signature):
                self._note(symbol(qualified), path, f'Identité syntaxique ambiguë : {qualified}#{member.signature}')
            else:
                self.facts.declaration(symbol(qualified), 'CONTAINS', symbol(qualified, member.signature), path,
                                       member.name_line)
        for item in java_type.fields:
            self.facts.declaration(symbol(qualified), 'CONTAINS', symbol(qualified, item.name), path, item.line)
            if item.qualified_type is not None:
                self.facts.declaration(symbol(qualified, item.name), 'TYPED_AS', symbol(item.qualified_type), path,
                                       item.line)
        for accessor in accessors.declarations(java_type):
            self.facts.accessor(symbol(qualified), symbol(qualified, accessor.signature), path, accessor.name_line,
                                accessors.premises(qualified, accessor))
        for supertype in java_type.clauses:
            if self.index.get(supertype.qualified or '') is not None:
                self.facts.declaration(symbol(qualified), supertype_relation(java_type, supertype),
                                       symbol(supertype.qualified), path, supertype.line)

    def _site(self, java_file, site):
        java_type = self.index.get(site.owner).java_type
        if site.owner in self.index.duplicated or (site.member is not None and java_type.ambiguous(site.member)):
            return  # Le proprietaire n'a pas d'identite unique : la note de sa declaration le dit deja.
        self.seen += 1
        subject = symbol(site.owner, site.member) if site.member is not None else symbol(site.owner)
        outcome = self.resolver.resolve(site, java_file)
        if outcome.target is None:
            self.reasons[outcome.reason] += 1
            self._unread.setdefault((subject, java_file.path), []).append(site_diagnostic(site, outcome))
            return
        self.resolved += 1
        for holder, relation, target, line in outcome.declarations:
            self.facts.declaration(holder, relation, target, java_file.path, line)
        self.facts.call(subject, outcome.target, java_file.path, site, outcome.premises, outcome.counter_examples)

    def _note(self, subject, path, note):
        notes = self._notes.setdefault((subject, path), [])
        if note not in notes:
            notes.append(note)
