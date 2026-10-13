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

def minia(provider=None, url=None, model=None, claude_model=None, gemini_model=None, mistral_model=None,
          claude_sonnet_model=None, gemini_lite_model=None):
    """Reglages de Minia : fournisseur par defaut, puis chaque fournisseur. Un fournisseur sans modele reste
    desactive ; sans aucun, Minia est desactivee. Claude et Gemini ne s'activent que sur choix explicite
    d'un modele (MINIA_CLAUDE_MODEL, MINIA_GEMINI_MODEL) : ce sont des services distants. MINIA_GEMINI_TIER
    dit si la cle Gemini est au niveau gratuit (defaut : les donnees peuvent servir a Google) ou payant ;
    MINIA_MISTRAL_MODEL et MINIA_MISTRAL_TIER font de meme pour Mistral ; MINIA_MISTRAL_NUM_CTX donne la
    fenetre du modele Mistral choisi, en tokens. MINIA_CLAUDE_SONNET_MODEL ajoute un second modele Claude a cote du
    premier ; MINIA_GEMINI_LITE_MODEL et MINIA_GEMINI_LITE_TIER, un second modele Gemini."""
    return {'provider': (provider or os.getenv('MINIA_PROVIDER', 'ollama')).strip().lower(),
            'url': url or os.getenv('MINIA_OLLAMA_URL', 'http://127.0.0.1:11434'),
            'model': (model if model is not None else os.getenv('MINIA_OLLAMA_MODEL', '')).strip(),
            'num_ctx': int(os.getenv('MINIA_OLLAMA_NUM_CTX', '16384')),
            'timeout': float(os.getenv('MINIA_OLLAMA_TIMEOUT_SECONDS', '900')),
            'claude_model': (claude_model if claude_model is not None
                             else os.getenv('MINIA_CLAUDE_MODEL', '')).strip(),
            'gemini_model': (gemini_model if gemini_model is not None
                             else os.getenv('MINIA_GEMINI_MODEL', '')).strip(),
            'gemini_tier': os.getenv('MINIA_GEMINI_TIER', 'free').strip().lower(),
            'mistral_model': (mistral_model if mistral_model is not None
                              else os.getenv('MINIA_MISTRAL_MODEL', '')).strip(),
            'mistral_tier': os.getenv('MINIA_MISTRAL_TIER', 'free').strip().lower(),
            'mistral_num_ctx': int(os.getenv('MINIA_MISTRAL_NUM_CTX', '32768')),
            'claude_sonnet_model': (claude_sonnet_model if claude_sonnet_model is not None
                                    else os.getenv('MINIA_CLAUDE_SONNET_MODEL', '')).strip(),
            'gemini_lite_model': (gemini_lite_model if gemini_lite_model is not None
                                  else os.getenv('MINIA_GEMINI_LITE_MODEL', '')).strip(),
            'gemini_lite_tier': os.getenv('MINIA_GEMINI_LITE_TIER', 'free').strip().lower()}

def minia_max_calls(value=None):
    """Le plus d'opérations que Minia choisit dans une exploration (MINIA_MAX_CALLS, défaut 8). Les vérifications
    d'affirmations viennent en plus, dans la limite de l'échange avec Taxo."""
    return int(value if value is not None else os.getenv('MINIA_MAX_CALLS', '8'))


def minia_trace(value=None):
    """Journal de développement des échanges dans la console (MINIA_TRACE) : off (défaut), summary ou full."""
    return (value or os.getenv('MINIA_TRACE', 'off')).strip().lower()


def minia_exchange_bytes(value=None):
    """Le budget d'un échange d'exploration, en octets (MINIA_EXCHANGE_BYTES, défaut 64 000) ; jamais plus que la
    fenêtre du modèle."""
    return int(value if value is not None else os.getenv('MINIA_EXCHANGE_BYTES', '64000'))


def minia_source_context(value=None):
    """Code source que Minia peut recevoir : `off` (defaut, aucun) ou `diff` (le diff d'un commit, sur
    accord de chaque demande). Avec un Ollama distant, `diff` fait sortir du code de la machine."""
    return (value or os.getenv('MINIA_SOURCE_CONTEXT', 'off')).strip().lower()


def taxo_source_reading(value=None):
    """Lecture du code d'un symbole par le protocole (`get_source`) : `off` (defaut) ou `symbol`, sur accord de chaque
    echange. Reglage distinct de MINIA_SOURCE_CONTEXT : l'accord du diff n'autorise jamais la lecture du code."""
    return (value or os.getenv('TAXO_SOURCE_READING', 'off')).strip().lower()


def minia_investigations(path=None, days=None):
    """Le carnet des enquêtes navigables de Minia (récit TAXO-MINIA-ENQUETE-01) : un fichier SQLite propre à Minia
    (`MINIA_INVESTIGATIONS_DB`), créé à la première enquête, et la durée d'inactivité après laquelle une enquête
    n'est plus restituée (`MINIA_INVESTIGATION_DAYS`, 7 par défaut)."""
    default = Path.home() / '.cache' / 'taxo' / 'minia' / 'investigations.sqlite3'
    days = days if days is not None else int(os.getenv('MINIA_INVESTIGATION_DAYS', '7'))
    if days <= 0:
        raise ValueError(f'MINIA_INVESTIGATION_DAYS invalide : {days} (un nombre de jours positif).')
    return {'path': Path(path or os.getenv('MINIA_INVESTIGATIONS_DB') or default), 'days': days}
