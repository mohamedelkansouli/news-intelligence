"""
nlp.py — Extraction NLP (noms, noms propres) vers MotherDuck
=============================================================
Traite uniquement les articles PAS encore dans article_words (incrémental).
Langues : EN et FR via spaCy, AR via tokenisation simple.

Usage :
    python nlp.py
    MOTHERDUCK_TOKEN=xxx python nlp.py
"""
import os
import re
import time
import logging
import duckdb
import spacy

# ═══════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

MAX_CHARS   = 20_000   # tronque les textes trop longs
BATCH_SIZE  = 50_000   # insertions par lot


# ═══════════════════════════════════════════════════════
# CONNEXION
# ═══════════════════════════════════════════════════════
def get_connection() -> duckdb.DuckDBPyConnection:
    md_token = os.environ.get("MOTHERDUCK_TOKEN")
    if not md_token:
        with open("cfg/secrets.cfg") as f:
            md_token = f.read().split("=", 1)[1].strip().strip("'\"")

    con = duckdb.connect(f"md:?motherduck_token={md_token}")
    con.execute("USE news_intelligence")
    logger.info("✅ Connecté à MotherDuck : news_intelligence")
    return con


# ═══════════════════════════════════════════════════════
# CHARGEMENT MODÈLES
# ═══════════════════════════════════════════════════════
def load_models() -> dict:
    logger.info("Chargement des modèles spaCy…")
    return {
        "en": spacy.load("en_core_web_sm", disable=["ner", "textcat"]),
        "fr": spacy.load("fr_core_news_sm", disable=["ner", "textcat"]),
    }


# ═══════════════════════════════════════════════════════
# TOKENISATION ARABE (sans modèle spaCy)
# ═══════════════════════════════════════════════════════
_AR_STOP = {
    "في", "من", "على", "إلى", "عن", "مع", "هذا", "هذه", "التي", "الذي",
    "كان", "كانت", "أن", "لا", "ما", "كل", "قد", "أو", "وقد", "وكان",
    "بعد", "قبل", "حتى", "عند", "أكثر", "لقد", "ولا", "وإن",
}

def tokenize_arabic(text: str) -> list[str]:
    """Extrait les mots arabes d'au moins 3 caractères hors stopwords."""
    words = re.findall(r"[\u0600-\u06FF]{3,}", text)
    return [w for w in words if w not in _AR_STOP]


# ═══════════════════════════════════════════════════════
# EXTRACTION MOTS PAR ARTICLE
# ═══════════════════════════════════════════════════════
def extract_words(article_id: str, lang: str, text: str, nlp_models: dict) -> list[tuple]:
    text = text[:MAX_CHARS]

    if lang == "ar":
        mots = tokenize_arabic(text)
        return [(article_id, m.lower()) for m in mots if m]

    nlp = nlp_models.get(lang, nlp_models["en"])
    doc = nlp(text)
    return [
        (article_id, token.text.lower().strip())
        for token in doc
        if token.pos_ in ("NOUN", "PROPN")
        and len(token.text.strip()) > 1
    ]


# ═══════════════════════════════════════════════════════
# PIPELINE PRINCIPAL
# ═══════════════════════════════════════════════════════
def run_nlp():
    con = get_connection()
    nlp_models = load_models()

    # Articles pas encore traités (incrémental)
    logger.info("Récupération des articles non traités…")
    articles = con.execute("""
        SELECT a.article_id, a.language, a.text
        FROM articles a
        LEFT JOIN article_words w ON a.article_id = w.article_id
        WHERE a.text IS NOT NULL
          AND a.text != ''
          AND w.article_id IS NULL
    """).fetchall()

    if not articles:
        logger.info("✅ Aucun nouvel article à traiter.")
        con.close()
        return

    logger.info(f"{len(articles)} articles à traiter")

    start      = time.time()
    total_mots = 0
    batch_mots = []
    errors     = 0

    for i, (article_id, lang, text) in enumerate(articles):
        try:
            mots = extract_words(article_id, lang, text, nlp_models)
            batch_mots.extend(mots)
        except Exception as e:
            logger.warning(f"  ⚠️  article {article_id} : {e}")
            errors += 1

        # Insertion par lot
        if len(batch_mots) >= BATCH_SIZE:
            con.executemany("INSERT INTO article_words VALUES (?, ?)", batch_mots)
            total_mots += len(batch_mots)
            batch_mots  = []

        # Log de progression
        if (i + 1) % 500 == 0:
            elapsed  = time.time() - start
            vitesse  = (i + 1) / elapsed
            eta      = (len(articles) - (i + 1)) / vitesse
            logger.info(
                f"  {i+1}/{len(articles)} "
                f"({(i+1)/len(articles)*100:.1f}%) | "
                f"{total_mots:,} mots | "
                f"{elapsed:.0f}s | "
                f"{vitesse:.1f} art/s | "
                f"ETA : {eta/60:.0f} min"
            )

    # Dernier lot
    if batch_mots:
        con.executemany("INSERT INTO article_words VALUES (?, ?)", batch_mots)
        total_mots += len(batch_mots)

    elapsed = time.time() - start
    logger.info("=" * 60)
    logger.info(f"✅ {total_mots:,} mots insérés en {elapsed:.0f}s ({elapsed/60:.1f} min)")
    logger.info(f"   Articles traités : {len(articles)} | Erreurs : {errors}")
    logger.info("=" * 60)

    con.close()


if __name__ == "__main__":
    run_nlp()