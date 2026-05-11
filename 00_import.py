import duckdb

con = duckdb.connect("/home/simo/Documents/news-intelligence/news.duckdb")

con.execute("INSERT INTO articles SELECT * FROM 'articles.parquet'")
con.execute("INSERT INTO article_words SELECT * FROM 'article_words.parquet'")

print("Articles  :", con.execute("SELECT COUNT(*) FROM articles").fetchone()[0])
print("Mots      :", con.execute("SELECT COUNT(*) FROM article_words").fetchone()[0])