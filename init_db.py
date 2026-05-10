"""
init_db.py — Création des tables sur MotherDuck
================================================
Lance une fois pour initialiser le schéma.
Idempotent : peut être relancé sans risque.

Usage :
    python init_db.py
"""
import os
import duckdb

def main():
    # Lire le token
    md_token = os.environ.get("MOTHERDUCK_TOKEN")
    if not md_token:
        with open("cfg/secrets.cfg", "r") as f:
            md_token = f.read().split("=", 1)[1].strip().strip("'\"")
    
    # Connexion
    print("→ Connexion à MotherDuck...")
    con = duckdb.connect(f"md:?motherduck_token={md_token}")
    con.execute("CREATE DATABASE IF NOT EXISTS news_intelligence")
    con.execute("USE news_intelligence")
    print("✅ Connecté à news_intelligence")
    
    # Création des tables
    print("\n→ Création des tables...")
    
    con.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            article_id      VARCHAR PRIMARY KEY,
            url             VARCHAR NOT NULL,
            url_normalized  VARCHAR,
            source_name     VARCHAR,
            source_domain   VARCHAR,
            language        VARCHAR,
            title           VARCHAR,
            author          VARCHAR,
            publish_date    TIMESTAMP,
            fetch_date      TIMESTAMP,
            text            VARCHAR,
            fetch_method    VARCHAR
        )
    """)
    print("  ✅ articles")
    
    con.execute("""
        CREATE TABLE IF NOT EXISTS article_tokens (
            article_id  VARCHAR NOT NULL,
            token       VARCHAR NOT NULL
        )
    """)
    print("  ✅ article_tokens")
    
    con.execute("""
        CREATE TABLE IF NOT EXISTS article_words (
            article_id  VARCHAR NOT NULL,
            word        VARCHAR NOT NULL
        )
    """)
    print("  ✅ article_words")
    
    con.execute("""
        CREATE TABLE IF NOT EXISTS stopwords (
            language    VARCHAR NOT NULL,
            word        VARCHAR NOT NULL
        )
    """)
    print("  ✅ stopwords")
    
    # Index
    print("\n→ Création des index...")
    con.execute("CREATE INDEX IF NOT EXISTS idx_articles_date ON articles(publish_date)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_articles_lang ON articles(language)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_articles_source ON articles(source_name)")
    print("  ✅ Index créés")
    
    # Résumé
    print("\n" + "="*60)
    for table in ["articles", "article_tokens", "article_words", "stopwords"]:
        n = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table:<20} {n:>10} lignes")
    print("="*60)
    print("✅ Initialisation terminée")
    
    con.close()

if __name__ == "__main__":
    main()