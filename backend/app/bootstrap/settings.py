import os
from pathlib import Path

def database_url(value=None):
    return value or os.getenv('DATABASE_URL', 'postgresql+psycopg://taxo:taxo@localhost:5432/taxo')

def allowed_roots(value=None):
    return [Path(p).resolve() for p in (value or os.getenv('TAXO_ALLOWED_ROOTS', str(Path.cwd())).split(os.pathsep))]

def hypotheses_models(value=None):
    """Modeles a preparer au demarrage : TAXO_HYPOTHESES vide = mode documentaire, rien n'est telecharge."""
    raw = value if value is not None else os.getenv('TAXO_HYPOTHESES', '')
    return [name.strip() for name in raw.split(',') if name.strip()]

def minia(provider=None, url=None, model=None):
    """Reglages de Minia : fournisseur, adresse et modele. Sans modele, Minia reste desactivee."""
    return {'provider': (provider or os.getenv('MINIA_PROVIDER', 'ollama')).strip().lower(),
            'url': url or os.getenv('MINIA_OLLAMA_URL', 'http://127.0.0.1:11434'),
            'model': (model if model is not None else os.getenv('MINIA_OLLAMA_MODEL', '')).strip(),
            'num_ctx': int(os.getenv('MINIA_OLLAMA_NUM_CTX', '16384'))}

def minia_source_context(value=None):
    """Code source que Minia peut recevoir : `off` (defaut, aucun) ou `diff` (le diff d'un commit, sur
    accord de chaque demande). Avec un Ollama distant, `diff` fait sortir du code de la machine."""
    return (value or os.getenv('MINIA_SOURCE_CONTEXT', 'off')).strip().lower()
