from app.evaluations.domain.evaluator import EvaluatorCatalog

CATALOG = EvaluatorCatalog(
    catalog_id='spring-boot',
    catalog_version='1',
    relations=('BUILT_FROM', 'SERVED_BY'),
    coverage_types=('ANALYSED', 'NOT_INTERPRETED', 'READ_ERROR'),
)
