from app.evaluations.domain.evaluator import EvaluatorCatalog


CATALOG = EvaluatorCatalog(
    catalog_id='inventory',
    # Version 2 (décision « Taxo témoin », D4) : un fichier binaire est dit hors du périmètre de lecture.
    catalog_version='2',
    relations=('CONTAINS', 'DECLARED_BY', 'USES_TECHNOLOGY', 'WRITTEN_IN'),
    coverage_types=('ANALYSED', 'NOT_INTERPRETED', 'OUT_OF_SCOPE', 'READ_ERROR'),
    languages=None,  # TAXO-COV-01 : indépendant du langage
)
