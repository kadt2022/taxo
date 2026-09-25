from app.evaluations.domain.evaluator import EvaluatorCatalog


CATALOG = EvaluatorCatalog(
    catalog_id='git',
    catalog_version='1',
    relations=('AUTHORED_BY', 'CHANGES', 'CHILD_OF', 'HAS_COMMIT'),
    coverage_types=('ANALYSED', 'NOT_INTERPRETED'),
)
