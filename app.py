import os
import streamlit as st
import duckdb
from wordcloud import WordCloud
import matplotlib.pyplot as plt
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Word Cloud Dashboard", layout="wide")
st.title("📊 Nuage de mots - Articles d'actualité")

@st.cache_resource
def get_connection():
    md_token = os.environ.get("MOTHERDUCK_TOKEN")
    if not md_token:
        with open("cfg/secrets.cfg") as f:
            md_token = f.read().split("=", 1)[1].strip().strip("'\"")
    con = duckdb.connect(f"md:?motherduck_token={md_token}")
    con.execute("USE news_intelligence")
    return con

con = get_connection()

# === SIDEBAR ===
st.sidebar.header("Filtres")

sources_raw = con.execute("SELECT DISTINCT source_name FROM articles ORDER BY source_name").fetchall()
sources_list = ["Toutes"] + [s[0] for s in sources_raw if s[0] is not None]
source = st.sidebar.selectbox("Source", sources_list)

languages_raw = con.execute("SELECT DISTINCT language FROM articles ORDER BY language").fetchall()
languages_list = ["Toutes"] + [l[0] for l in languages_raw if l[0] is not None]
language = st.sidebar.selectbox("Langue", languages_list)

min_date, max_date = con.execute("SELECT MIN(publish_date)::DATE, MAX(publish_date)::DATE FROM articles").fetchone()
if min_date and max_date:
    date_range = st.sidebar.date_input("Période", value=[min_date, max_date], min_value=min_date, max_value=max_date)
else:
    date_range = []

max_words = st.sidebar.slider("Nombre de mots dans le nuage", 50, 300, 100)

# === BUILD WHERE ===
filters = []
filter_params = []

if source != "Toutes":
    filters.append("a.source_name = ?")
    filter_params.append(source)
if language != "Toutes":
    filters.append("a.language = ?")
    filter_params.append(language)
if len(date_range) == 2:
    filters.append("a.publish_date::DATE >= ? AND a.publish_date::DATE <= ?")
    filter_params.extend([date_range[0], date_range[1]])

where_clause = " AND ".join(filters) if filters else "1=1"

# === WORD CLOUD ===
st.subheader("☁️ Nuage de mots")

query_cloud = f"""
    SELECT w.word, COUNT(*) as count
    FROM article_words w
    JOIN articles a ON w.article_id = a.article_id
    WHERE {where_clause}
    GROUP BY w.word
    ORDER BY count DESC
"""

word_counts = con.execute(query_cloud, filter_params).fetchall()

if word_counts:
    words_dict = {word: count for word, count in word_counts}
    wordcloud = WordCloud(width=1200, height=500, background_color="white", max_words=max_words, colormap="viridis")
    wordcloud.generate_from_frequencies(words_dict)
    fig, ax = plt.subplots(figsize=(18, 7))
    ax.imshow(wordcloud, interpolation="bilinear")
    ax.axis("off")
    st.pyplot(fig)
else:
    st.warning("Aucun résultat avec ces filtres")

# === GRAPHIQUE ÉVOLUTION ===
st.subheader("📈 Évolution des mots dans le temps (fréquence relative)")

top_words = [w[0] for w in word_counts[:200]] if word_counts else []

if top_words:
    selected_words = st.multiselect(
        "Choisir un ou plusieurs mots à suivre :",
        top_words,
        default=[top_words[0]] if top_words else [],
        key="word_multiselect"
    )

    if selected_words:
        mots_escaped = ", ".join([f"'{w.replace(chr(39), chr(39)+chr(39))}'" for w in selected_words])

        query_trend = f"""
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
            SELECT d.date, d.word as Mot, d.count * 1.0 / t.total AS Fréquence
            FROM daily_counts d
            JOIN daily_totals t ON d.date = t.date
            ORDER BY d.date
        """

        trend_data = con.execute(query_trend, filter_params).fetchall()

        if trend_data:
            df_trend = pd.DataFrame(trend_data, columns=["Date", "Mot", "Fréquence"])
            fig_trend = px.line(df_trend, x="Date", y="Fréquence", color="Mot",
                                title="Fréquence relative (corrigée du volume)", markers=True, line_shape="spline")
            fig_trend.update_layout(height=450)
            st.plotly_chart(fig_trend, use_container_width=True)
        else:
            st.info("Aucune donnée pour ces mots avec ces filtres")
    else:
        st.info("Sélectionnez au moins un mot")
else:
    st.info("Sélectionnez des filtres pour voir les mots disponibles")