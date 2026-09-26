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

def minia(provider=None, url=None, model=None, claude_model=None, gemini_model=None, mistral_model=None):
    """Reglages de Minia : fournisseur par defaut, puis chaque fournisseur. Un fournisseur sans modele reste
    desactive ; sans aucun, Minia est desactivee. Claude et Gemini ne s'activent que sur choix explicite
    d'un modele (MINIA_CLAUDE_MODEL, MINIA_GEMINI_MODEL) : ce sont des services distants. MINIA_GEMINI_TIER
    dit si la cle Gemini est au niveau gratuit (defaut : les donnees peuvent servir a Google) ou payant ;
    MINIA_MISTRAL_MODEL et MINIA_MISTRAL_TIER font de meme pour Mistral ; MINIA_MISTRAL_NUM_CTX donne la
    fenetre du modele Mistral choisi, en tokens."""
    return {'provider': (provider or os.getenv('MINIA_PROVIDER', 'ollama')).strip().lower(),
            'url': url or os.getenv('MINIA_OLLAMA_URL', 'http://127.0.0.1:11434'),
            'model': (model if model is not None else os.getenv('MINIA_OLLAMA_MODEL', '')).strip(),
            'num_ctx': int(os.getenv('MINIA_OLLAMA_NUM_CTX', '16384')),
            'claude_model': (claude_model if claude_model is not None
                             else os.getenv('MINIA_CLAUDE_MODEL', '')).strip(),
            'gemini_model': (gemini_model if gemini_model is not None
                             else os.getenv('MINIA_GEMINI_MODEL', '')).strip(),
            'gemini_tier': os.getenv('MINIA_GEMINI_TIER', 'free').strip().lower(),
            'mistral_model': (mistral_model if mistral_model is not None
                              else os.getenv('MINIA_MISTRAL_MODEL', '')).strip(),
            'mistral_tier': os.getenv('MINIA_MISTRAL_TIER', 'free').strip().lower(),
            'mistral_num_ctx': int(os.getenv('MINIA_MISTRAL_NUM_CTX', '32768'))}

def minia_source_context(value=None):
    """Code source que Minia peut recevoir : `off` (defaut, aucun) ou `diff` (le diff d'un commit, sur
    accord de chaque demande). Avec un Ollama distant, `diff` fait sortir du code de la machine."""
    return (value or os.getenv('MINIA_SOURCE_CONTEXT', 'off')).strip().lower()
