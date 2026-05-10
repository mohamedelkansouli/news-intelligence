"""
nlp.py — Extraction NLP multilingue (EN, FR, AR)
=================================================
- EN, FR : spaCy (rapide)
- AR     : Stanza (POS tagging arabe propre)

Usage :
    python nlp.py

Première exécution : Stanza télécharge ~500 MB pour l'arabe.
"""
import time
import logging
import duckdb
import spacy
import stanza

# ═══════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════
DB_PATH = os.environ.get("DB_PATH", "/home/simo/Documents/news-intelligence/news.duckdb")
MAX_CHARS  = 20_000
BATCH_SIZE = 50_000

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════
# CHARGEMENT MODÈLES
# ═══════════════════════════════════════════════════════
def load_models():
    logger.info("Chargement spaCy EN/FR…")
    nlp_en = spacy.load("en_core_web_sm", disable=["ner", "textcat"])
    nlp_fr = spacy.load("fr_core_news_sm", disable=["ner", "textcat"])

    logger.info("Chargement Stanza AR (téléchargement automatique si absent)…")
    try:
        nlp_ar = stanza.Pipeline("ar", processors="tokenize,pos",
                                 use_gpu=False, verbose=False)
    except Exception:
        logger.info("Téléchargement du modèle arabe Stanza…")
        stanza.download("ar", verbose=False)
        nlp_ar = stanza.Pipeline("ar", processors="tokenize,pos",
                                 use_gpu=False, verbose=False)

    return {"en": nlp_en, "fr": nlp_fr, "ar": nlp_ar}


# ═══════════════════════════════════════════════════════
# EXTRACTION
# ═══════════════════════════════════════════════════════
def extract_spacy(article_id, text, nlp):
    doc = nlp(text)
    return [
        (article_id, t.text.lower().strip())
        for t in doc
        if t.pos_ in ("NOUN", "PROPN") and len(t.text.strip()) > 1
    ]

def extract_stanza(article_id, text, nlp):
    doc  = nlp(text)
    rows = []
    for sent in doc.sentences:
        for word in sent.words:
            if word.upos in ("NOUN", "PROPN") and len(word.text.strip()) > 1:
                rows.append((article_id, word.text.lower().strip()))
    return rows

def extract_words(article_id, lang, text, models):
    text = text[:MAX_CHARS]
    if lang == "ar":
        return extract_stanza(article_id, text, models["ar"])
    nlp = models.get(lang, models["en"])
    return extract_spacy(article_id, text, nlp)


# ═══════════════════════════════════════════════════════
# PIPELINE
# ═══════════════════════════════════════════════════════
def run_nlp():
    con    = duckdb.connect(DB_PATH)
    models = load_models()

    logger.info("Récupération des articles non traités…")
    articles = con.execute("""
        SELECT a.article_id, a.language, a.text
        FROM articles a
        LEFT JOIN article_words w ON a.article_id = w.article_id
        WHERE a.text IS NOT NULL AND a.text != '' AND w.article_id IS NULL
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
            batch_mots.extend(extract_words(article_id, lang, text, models))
        except Exception as e:
            logger.warning(f"  ⚠️  {article_id} ({lang}) : {e}")
            errors += 1

        if len(batch_mots) >= BATCH_SIZE:
            con.executemany("INSERT INTO article_words VALUES (?, ?)", batch_mots)
            total_mots += len(batch_mots)
            batch_mots  = []

        if (i + 1) % 100 == 0:
            elapsed = time.time() - start
            vitesse = (i + 1) / elapsed
            eta     = (len(articles) - (i + 1)) / vitesse
            logger.info(
                f"  {i+1}/{len(articles)} "
                f"({(i+1)/len(articles)*100:.1f}%) | "
                f"{total_mots:,} mots | "
                f"{elapsed:.0f}s | "
                f"{vitesse:.1f} art/s | "
                f"ETA : {eta/60:.0f} min"
            )

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