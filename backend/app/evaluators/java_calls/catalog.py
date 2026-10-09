from app.evaluations.domain.evaluator import EvaluatorCatalog

# Version 1 (TAXO-01K, ARCHITECTURE § 14) : declarations des sources (CONTAINS, TYPED_AS, EXTENDS, IMPLEMENTS entre
# types) et appels resolus par `java.calls.declared-receiver-unique-target/1`, premier fragment.
CATALOG = EvaluatorCatalog(
    catalog_id='java-calls',
    catalog_version='1',
    relations=('CALLS', 'CONTAINS', 'EXTENDS', 'IMPLEMENTS', 'TYPED_AS'),
    coverage_types=('ANALYSED', 'NOT_INTERPRETED', 'READ_ERROR'),
    # TAXO-COV-01 : ce catalogue ne lit que les sources Java.
    languages=('Java',),
    # TAXO-01M : les raisons fermees de ses sites non resolus (ARCHITECTURE § 14), sorties du schema commun. Ce
    # sont exactement celles que la version 1 ecrivait deja : le catalogue ne change pas de sens ni de version.
    diagnostic_codes=('LAMBDA_OR_LOCAL_CONTEXT', 'NO_MATCHING_DECLARATION', 'OVERLOAD_AMBIGUOUS', 'PARSE_ERROR',
                      'RECEIVER_KIND_DEFERRED', 'RECEIVER_TYPE_AMBIGUOUS', 'RECEIVER_TYPE_UNKNOWN',
                      'SUPER_TYPE_UNRESOLVED', 'TARGET_DECLARATION_OUTSIDE_SNAPSHOT', 'TARGET_TYPE_OUTSIDE_SNAPSHOT',
                      'UNSUPPORTED_CALL_FORM'),
)
