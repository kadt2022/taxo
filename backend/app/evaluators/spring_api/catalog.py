from app.evaluations.domain.evaluator import EvaluatorCatalog


CATALOG = EvaluatorCatalog(
    catalog_id='spring-api',
    catalog_version='1',
    relations=('HANDLED_BY',),
    coverage_types=('ANALYSED', 'NOT_INTERPRETED', 'READ_ERROR'),
)
