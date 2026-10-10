from app.evaluations.domain.evaluator import EvaluatorCatalog

# Version 2 (TAXO-ID-01) : le qualificatif `filter_chain`, qui entre dans l'identite des faits, designe la
# methode par sa signature (`#chain(HttpSecurity)`) ; la version 1 la designait par son seul nom.
# Version 3 (TAXO-MINIA-SEC-01, E2) : securite de methode et CSRF. AUTHORIZED_BY vise aussi une methode gardee par
# `@PreAuthorize`, ANNOTATED_WITH dit le type qui l'active, CONFIGURES la desactivation de CSRF.


CATALOG = EvaluatorCatalog(
    catalog_id='spring-security',
    catalog_version='3',
    relations=('ANNOTATED_WITH', 'AUTHORIZED_BY', 'CONFIGURES', 'MATCHED_BY', 'PERMITS_ALL', 'PROTECTED_BY'),
    coverage_types=('ANALYSED', 'NOT_INTERPRETED', 'READ_ERROR'),
    # TAXO-COV-01 : ce que ce catalogue a toujours lu ; il ne couvre aucune autre source.
    languages=('Java',),
)
