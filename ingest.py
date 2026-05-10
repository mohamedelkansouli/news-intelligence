"""
ingest.py — Ingestion quotidienne RSS vers MotherDuck
======================================================
Récupère UNIQUEMENT les articles publiés aujourd'hui depuis 37 sources RSS.
Stocke dans MotherDuck avec déduplication automatique.

Usage :
    python ingest.py                           # lit cfg/secrets.cfg
    MOTHERDUCK_TOKEN=xxx python ingest.py      # ou via env var
"""
import os
import hashlib
import logging
from datetime import date, datetime
from urllib.parse import urlparse
import duckdb
import feedparser
import requests
from bs4 import BeautifulSoup
import trafilatura

# ═════════════════════════════════════════════════════════════════════════════
# CONFIG
# ═════════════════════════════════════════════════════════════════════════════
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
TIMEOUT = 12

# 37 sources validées (EN=14, FR=13, AR=10)
FEEDS = [
    ("BBC News","http://feeds.bbci.co.uk/news/rss.xml","bbc.com","en"),
    ("The Guardian","https://www.theguardian.com/international/rss","theguardian.com","en"),
    ("Engadget","https://www.engadget.com/rss.xml","engadget.com","en"),
    ("TechCrunch","https://techcrunch.com/feed/","techcrunch.com","en"),
    ("CNN","http://rss.cnn.com/rss/edition.rss","cnn.com","en"),
    ("Al Jazeera EN","https://www.aljazeera.com/xml/rss/all.xml","aljazeera.com","en"),
    ("NPR","https://feeds.npr.org/1001/rss.xml","npr.org","en"),
    ("The Independent","https://www.independent.co.uk/news/world/rss","independent.co.uk","en"),
    ("Vice","https://www.vice.com/en/rss","vice.com","en"),
    ("Wired","https://www.wired.com/feed/rss","wired.com","en"),
    ("Ars Technica","https://feeds.arstechnica.com/arstechnica/index","arstechnica.com","en"),
    ("Le Monde","https://www.lemonde.fr/rss/une.xml","lemonde.fr","fr"),
    ("Le Figaro","https://www.lefigaro.fr/rss/figaro_actualites.xml","lefigaro.fr","fr"),
    ("France 24","https://www.france24.com/fr/rss","france24.com","fr"),
    ("FranceInfo","https://www.francetvinfo.fr/titres.rss","francetvinfo.fr","fr"),
    ("L'Express","https://www.lexpress.fr/rss/alaune.xml","lexpress.fr","fr"),
    ("Mediapart","https://www.mediapart.fr/articles/feed","mediapart.fr","fr"),
    ("RFI","https://www.rfi.fr/fr/rss","rfi.fr","fr"),
    ("Courrier Inter.","https://www.courrierinternational.com/feed/all/rss.xml","courrierinternational.com","fr"),
    ("La Croix","https://www.la-croix.com/RSS/UNIVERS","la-croix.com","fr"),
    ("Slate FR","http://www.slate.fr/rss.xml","slate.fr","fr"),
    ("BFM TV","https://www.bfmtv.com/rss/news-24-7/","bfmtv.com","fr"),
    ("HuffPost FR","https://www.huffingtonpost.fr/feeds/index.xml","huffingtonpost.fr","fr"),
    ("Al Jazeera AR","https://www.aljazeera.net/aljazeerarss/a7c186be-1b17-4c9e-8dba-5d36fb2b2f97/73d2e1c9-cd6c-4087-aa22-7f78e370b68f","aljazeera.net","ar"),
    ("BBC Arabic","https://www.bbc.com/arabic/index.xml","bbc.com","ar"),
    ("RT Arabic","https://arabic.rt.com/rss/","arabic.rt.com","ar"),
    ("Hespress","https://fr.hespress.com/feed","hespress.com","ar"),
    ("Al Quds","https://www.alquds.co.uk/feed/","alquds.co.uk","ar"),
    ("Asharq Al-Awsat","https://aawsat.com/feed","aawsat.com","ar"),
    ("Al-Masry Al-Youm","https://www.almasryalyoum.com/rss/rssfeed","almasryalyoum.com","ar"),
    ("Saudi Gazette","https://saudigazette.com.sa/rssFeed/74","saudigazette.com.sa","ar"),
    ("Okaz","https://okaz.com.sa/rssFeed/190","okaz.com.sa","ar"),
    ("Arab News","https://www.arabnews.com/rss.xml","arabnews.com","ar"),
]

# ═════════════════════════════════════════════════════════════════════════════
# CONNEXION DB
# ═════════════════════════════════════════════════════════════════════════════
def get_connection():
    """Connexion MotherDuck (token depuis env var ou cfg/secrets.cfg)."""
    md_token = os.environ.get("MOTHERDUCK_TOKEN")
    
    if not md_token:
        with open("cfg/secrets.cfg", "r") as f:
            md_token = f.read().split("=", 1)[1].strip().strip("'\"")
    
    con = duckdb.connect(f"md:?motherduck_token={md_token}")
    con.execute("CREATE DATABASE IF NOT EXISTS news_intelligence")
    con.execute("USE news_intelligence")
    logger.info("✅ Connecté à MotherDuck: news_intelligence")
    return con

# ═════════════════════════════════════════════════════════════════════════════
# PARSING RSS
# ═════════════════════════════════════════════════════════════════════════════
def parse_feed(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        feed = feedparser.parse(r.content)
        if not feed.bozo and feed.entries:
            return list(feed.entries)
    except: pass
    
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        soup = BeautifulSoup(r.text, "xml")
        items = soup.find_all("item") or soup.find_all("entry")
        entries = []
        for item in items:
            title_t = item.find("title")
            link_t = item.find("link")
            link = (link_t.text or "").strip() or link_t.get("href", "") if link_t else ""
            entries.append({"title": title_t.text if title_t else "", "link": link})
        return entries
    except:
        return []

def get_link(entry):
    if isinstance(entry, dict):
        return entry.get("link", "")
    link = entry.get("link", "")
    if not link:
        links = entry.get("links", [])
        if links:
            link = links[0].get("href", "")
    return link

def normalize_url(url):
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}{p.path}".rstrip("/").lower()

def article_id_from_url(url):
    return hashlib.sha256(normalize_url(url).encode("utf-8")).hexdigest()

# ═════════════════════════════════════════════════════════════════════════════
# EXTRACTION CONTENU
# ═════════════════════════════════════════════════════════════════════════════
def extract_content(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        text = trafilatura.extract(r.text, include_comments=False, include_tables=False, no_fallback=False)
        if not text or len(text) < 100:
            return None
        
        metadata = trafilatura.extract_metadata(r.text)
        return {
            "text": text,
            "title": metadata.title if metadata and metadata.title else None,
            "author": metadata.author if metadata and metadata.author else None,
            "publish_date": metadata.date if metadata and metadata.date else None,
        }
    except:
        return None

# ═════════════════════════════════════════════════════════════════════════════
# INGESTION
# ═════════════════════════════════════════════════════════════════════════════
def ingest():
    con = get_connection()
    today = str(date.today())
    
    stats = {"sources": 0, "found": 0, "today": 0, "inserted": 0, "skipped": 0}
    
    for source_name, rss_url, domain, lang in FEEDS:
        logger.info(f"📥 {source_name} ({lang})...")
        stats["sources"] += 1
        
        entries = parse_feed(rss_url)
        if not entries:
            logger.warning(f"  ⚠️  Aucun article")
            continue
        
        stats["found"] += len(entries)
        
        for entry in entries:
            url = get_link(entry)
            if not url:
                continue
            
            article_id = article_id_from_url(url)
            
            # Déjà en DB ?
            if con.execute("SELECT 1 FROM articles WHERE article_id = ?", [article_id]).fetchone():
                stats["skipped"] += 1
                continue
            
            # Extraire
            content = extract_content(url)
            if not content:
                stats["skipped"] += 1
                continue
            
            # FILTRE DATE : seulement aujourd'hui
            if content.get("publish_date"):
                try:
                    article_date = content["publish_date"][:10]
                    if article_date != today:
                        stats["skipped"] += 1
                        continue
                    stats["today"] += 1
                except:
                    stats["skipped"] += 1
                    continue
            else:
                stats["skipped"] += 1
                continue
            
            # Insérer
            try:
                con.execute("""
                    INSERT INTO articles (
                        article_id, url, url_normalized, source_name, source_domain,
                        language, title, author, publish_date, fetch_date, text, fetch_method
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, [
                    article_id, url, normalize_url(url), source_name, domain,
                    lang, content["title"], content["author"], content["publish_date"],
                    datetime.now(), content["text"], "rss"
                ])
                stats["inserted"] += 1
            except Exception as e:
                logger.error(f"  ❌ {e}")
    
    con.close()
    
    logger.info("\n" + "="*60)
    logger.info(f"✅ TERMINÉ")
    logger.info(f"  Sources         : {stats['sources']}")
    logger.info(f"  Articles trouvés: {stats['found']}")
    logger.info(f"  Publiés auj.    : {stats['today']}")
    logger.info(f"  Insérés en DB   : {stats['inserted']}")
    logger.info(f"  Skippés         : {stats['skipped']}")
    logger.info("="*60)

if __name__ == "__main__":
    ingest()