from app.evaluations.domain.evaluator import EvaluatorCatalog


CATALOG = EvaluatorCatalog(
    catalog_id='spring-security',
    catalog_version='1',
    relations=('AUTHORIZED_BY', 'MATCHED_BY', 'PERMITS_ALL', 'PROTECTED_BY'),
    coverage_types=('ANALYSED', 'NOT_INTERPRETED', 'READ_ERROR'),
)
