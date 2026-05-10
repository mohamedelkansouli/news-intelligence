"""
api.py — API FastAPI locale sur ThinkCentre
============================================
Expose news.duckdb via HTTP pour Streamlit Cloud.
Sécurisé par token simple.

Usage :
    uvicorn api:app --host 0.0.0.0 --port 8000
"""
import os
import duckdb
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel

# ═══════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════
DB_PATH   = os.environ.get("DB_PATH", "/home/simo/Documents/news-intelligence/news.duckdb")
API_TOKEN = os.environ.get("API_TOKEN", "")   # obligatoire en prod

app = FastAPI()


# ═══════════════════════════════════════════════════════
# AUTH
# ═══════════════════════════════════════════════════════
def check_token(authorization: str = Header(...)):
    if not API_TOKEN:
        raise HTTPException(500, "API_TOKEN non configuré")
    if authorization != f"Bearer {API_TOKEN}":
        raise HTTPException(401, "Token invalide")


# ═══════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════
class QueryRequest(BaseModel):
    sql: str
    params: list = []


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/query")
def query(req: QueryRequest, authorization: str = Header(...)):
    check_token(authorization)
    try:
        con = duckdb.connect(DB_PATH, read_only=True)
        result = con.execute(req.sql, req.params).fetchall()
        columns = [desc[0] for desc in con.description]
        con.close()
        return {"columns": columns, "rows": result}
    except Exception as e:
        raise HTTPException(400, str(e))
