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
)
