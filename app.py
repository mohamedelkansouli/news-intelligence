import os
import re
import requests
import streamlit as st
from wordcloud import WordCloud
import matplotlib.pyplot as plt
import pandas as pd
import plotly.express as px
import arabic_reshaper
from bidi.algorithm import get_display

st.set_page_config(page_title="Word Cloud Dashboard", layout="wide")
st.title("📊 Nuage de mots - Articles d'actualité")

# ═══════════════════════════════════════════════════════
# CONNEXION API
# ═══════════════════════════════════════════════════════
API_URL   = os.environ.get("API_URL")   or st.secrets.get("API_URL")
API_TOKEN = os.environ.get("API_TOKEN") or st.secrets.get("API_TOKEN")

def run_query(sql, params=None):
    resp = requests.post(
        f"{API_URL}/query",
        json={"sql": sql, "params": params or []},
        headers={"Authorization": f"Bearer {API_TOKEN}"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["rows"]


# ═══════════════════════════════════════════════════════
# FONTS
# ═══════════════════════════════════════════════════════
ARABIC_REGEX = re.compile(r"[\u0600-\u06FF]")

def find_font(candidates):
    for path in candidates:
        if os.path.exists(path):
            return path
    return None

ARABIC_FONT = find_font([
    "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf",
])

LATIN_FONT = find_font([
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
])

def pick_font(words_dict):
    """Choisit la font selon le contenu du wordcloud."""
    arabic_count = sum(1 for w in words_dict if ARABIC_REGEX.search(w))
    latin_count  = len(words_dict) - arabic_count
    if arabic_count > latin_count and ARABIC_FONT:
        return ARABIC_FONT
    return LATIN_FONT

def reshape_arabic_dict(words_dict):
    """Reshape + bidi pour les mots arabes (laisse le reste intact)."""
    out = {}
    for word, count in words_dict.items():
        if ARABIC_REGEX.search(word):
            shaped = get_display(arabic_reshaper.reshape(word))
            out[shaped] = count
        else:
            out[word] = count
    return out


# ═══════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════
st.sidebar.header("Filtres")

sources_raw  = run_query("SELECT DISTINCT source_name FROM articles ORDER BY source_name")
sources_list = ["Toutes"] + [s[0] for s in sources_raw if s[0]]
source       = st.sidebar.selectbox("Source", sources_list)

languages_raw  = run_query("SELECT DISTINCT language FROM articles ORDER BY language")
languages_list = [l[0] for l in languages_raw if l[0]]
language       = st.sidebar.selectbox("Langue", languages_list)

date_row = run_query("SELECT MIN(publish_date)::DATE, MAX(publish_date)::DATE FROM articles")
min_date, max_date = date_row[0] if date_row else (None, None)
if min_date and max_date:
    date_range = st.sidebar.date_input("Période", value=[min_date, max_date])
else:
    date_range = []

max_words = st.sidebar.slider("Nombre de mots dans le nuage", 50, 300, 100)


# ═══════════════════════════════════════════════════════
# BUILD WHERE
# ═══════════════════════════════════════════════════════
filters       = []
filter_params = []

if source != "Toutes":
    filters.append("a.source_name = ?")
    filter_params.append(source)

if len(date_range) == 2:
    filters.append("a.publish_date::DATE >= ? AND a.publish_date::DATE <= ?")
    filter_params.extend([str(date_range[0]), str(date_range[1])])

where_clause = " AND ".join(filters) if filters else "1=1"


# ═══════════════════════════════════════════════════════
# WORD CLOUD
# ═══════════════════════════════════════════════════════
st.subheader("☁️ Nuage de mots")

word_counts = run_query(f"""
    SELECT w.word, COUNT(*) as count
    FROM article_words w
    JOIN articles a ON w.article_id = a.article_id
    WHERE {where_clause}
    GROUP BY w.word
    ORDER BY count DESC
""", filter_params)

if word_counts:
    words_dict = {w: c for w, c in word_counts}

    # Reshape uniquement les mots arabes
    words_dict_display = reshape_arabic_dict(words_dict)

    # Choix automatique de la font selon le contenu
    chosen_font = pick_font(words_dict)

    wc_kwargs = dict(
        width=1200, height=500,
        background_color="white",
        max_words=max_words,
        colormap="viridis",
    )
    if chosen_font:
        wc_kwargs["font_path"] = chosen_font

    wordcloud = WordCloud(**wc_kwargs)
    wordcloud.generate_from_frequencies(words_dict_display)

    fig, ax = plt.subplots(figsize=(18, 7))
    ax.imshow(wordcloud, interpolation="bilinear")
    ax.axis("off")
    st.pyplot(fig)
else:
    st.warning("Aucun résultat avec ces filtres")


# ═══════════════════════════════════════════════════════
# ÉVOLUTION TEMPORELLE
# ═══════════════════════════════════════════════════════
st.subheader("📈 Évolution des mots dans le temps (fréquence relative)")

top_words = [w[0] for w in word_counts[:200]] if word_counts else []

if top_words:
    selected_words = st.multiselect(
        "Choisir un ou plusieurs mots à suivre :",
        top_words,
        default=[top_words[0]] if top_words else [],
    )

    if selected_words:
        mots_escaped = ", ".join(
            [f"'{w.replace(chr(39), chr(39)+chr(39))}'" for w in selected_words]
        )

        trend_data = run_query(f"""
            WITH filtered AS (
                SELECT a.publish_date::DATE as date, w.word
                FROM article_words w
                JOIN articles a ON w.article_id = a.article_id
                WHERE {where_clause}
            ),
            daily_counts AS (
                SELECT date, word, COUNT(*) as count
                FROM filtered
                WHERE word IN ({mots_escaped})
                GROUP BY date, word
            ),
            daily_totals AS (
                SELECT date, COUNT(*) as total
                FROM filtered
                GROUP BY date
            )
            SELECT d.date, d.word, d.count * 1.0 / t.total AS freq
            FROM daily_counts d
            JOIN daily_totals t ON d.date = t.date
            ORDER BY d.date
        """, filter_params)

        if trend_data:
            df_trend  = pd.DataFrame(trend_data, columns=["Date", "Mot", "Fréquence"])
            fig_trend = px.line(
                df_trend, x="Date", y="Fréquence", color="Mot",
                title="Fréquence relative (corrigée du volume)",
                markers=True, line_shape="spline",
            )
            fig_trend.update_layout(height=450)
            st.plotly_chart(fig_trend, use_container_width=True)
        else:
            st.info("Aucune donnée pour ces mots avec ces filtres")
    else:
        st.info("Sélectionnez au moins un mot")
else:
    st.info("Sélectionnez des filtres pour voir les mots disponibles")