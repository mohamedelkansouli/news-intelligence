import duckdb
import os 

md_token = os.environ.get("MOTHERDUCK_TOKEN")
    
if not md_token:
    with open("cfg/secrets.cfg", "r") as f:
        md_token = f.read().split("=", 1)[1].strip().strip("'\"")

con = duckdb.connect(f"md:?motherduck_token={md_token}")
con.execute("USE news_intelligence")
con.execute("COPY (SELECT * FROM articles) TO 'articles.parquet'")
con.execute("COPY (SELECT * FROM article_words) TO 'article_words.parquet'")