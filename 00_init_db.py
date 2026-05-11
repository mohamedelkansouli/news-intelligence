import duckdb

con = duckdb.connect("/home/simo/Documents/news-intelligence/news.duckdb")

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

con.execute("""
    CREATE TABLE IF NOT EXISTS article_words (
        article_id  VARCHAR NOT NULL,
        word        VARCHAR NOT NULL
    )
""")

con.execute("CREATE INDEX IF NOT EXISTS idx_articles_date ON articles(publish_date)")
con.execute("CREATE INDEX IF NOT EXISTS idx_articles_lang ON articles(language)")
con.execute("CREATE INDEX IF NOT EXISTS idx_articles_source ON articles(source_name)")

print("✅ Tables créées")
con.close()