from app.evaluations.domain.evaluator import EvaluatorCatalog


CATALOG = EvaluatorCatalog(
    catalog_id='structure',
    catalog_version='1',
    relations=('BUILT_FROM', 'CONTAINS', 'DEPENDS_ON'),
    coverage_types=('ANALYSED', 'NOT_INTERPRETED', 'READ_ERROR'),
)
