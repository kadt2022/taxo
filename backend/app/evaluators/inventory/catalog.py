from app.evaluations.domain.evaluator import EvaluatorCatalog


CATALOG = EvaluatorCatalog(
    catalog_id='inventory',
    catalog_version='1',
    relations=('CONTAINS', 'DECLARED_BY', 'USES_TECHNOLOGY', 'WRITTEN_IN'),
    coverage_types=('ANALYSED', 'NOT_INTERPRETED', 'READ_ERROR'),
)
