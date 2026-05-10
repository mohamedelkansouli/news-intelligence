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

# ═══════════════════════════════════════════════════════
# PAGE CONFIG
# ═══════════════════════════════════════════════════════
st.set_page_config(
    page_title="The News Pattern",
    page_icon="◐",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ═══════════════════════════════════════════════════════
# CUSTOM STYLE
# ═══════════════════════════════════════════════════════
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    html, body, [class*="css"]  { font-family: 'Inter', sans-serif; }

    .block-container { padding-top: 2rem; padding-bottom: 3rem; max-width: 1400px; }

    h1 { font-weight: 700; letter-spacing: -0.02em; font-size: 2.4rem; margin-bottom: 0; }
    .subtitle { color: #6b7280; font-size: 1rem; margin-top: 0.2rem; margin-bottom: 2rem; font-weight: 400; }

    h2, h3 { font-weight: 600; letter-spacing: -0.01em; }

    section[data-testid="stSidebar"] { background-color: #fafafa; border-right: 1px solid #e5e7eb; }
    section[data-testid="stSidebar"] .block-container { padding-top: 2rem; }

    hr { margin-top: 0.5rem; margin-bottom: 1.5rem; border-color: #e5e7eb; }
</style>
""", unsafe_allow_html=True)

st.markdown("# The News Pattern")
st.markdown('<p class="subtitle">Tracking what the world is talking about — across languages, sources, time.</p>',
            unsafe_allow_html=True)
st.markdown("---")


# ═══════════════════════════════════════════════════════
# API
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
])


def reshape_arabic_dict(words_dict):
    return {get_display(arabic_reshaper.reshape(w)): c for w, c in words_dict.items()}


# ═══════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════
st.sidebar.markdown("### Filters")

sources_raw  = run_query("SELECT DISTINCT source_name FROM articles ORDER BY source_name")
sources_list = ["All"] + [s[0] for s in sources_raw if s[0]]
source       = st.sidebar.selectbox("Source", sources_list)

languages_raw  = run_query("SELECT DISTINCT language FROM articles ORDER BY language")
LANG_LABELS    = {"en": "English", "fr": "Français", "ar": "العربية"}
languages_list = ["All"] + [l[0] for l in languages_raw if l[0]]
language       = st.sidebar.selectbox(
    "Language",
    languages_list,
    format_func=lambda x: "All" if x == "All" else LANG_LABELS.get(x, x),
)

date_row = run_query("SELECT MIN(publish_date)::DATE, MAX(publish_date)::DATE FROM articles")
min_date, max_date = date_row[0] if date_row else (None, None)
if min_date and max_date:
    date_range = st.sidebar.date_input("Date range", value=[min_date, max_date])
else:
    date_range = []

max_words = st.sidebar.slider("Words to display", 50, 300, 120)

st.sidebar.markdown("---")
st.sidebar.caption("The News Pattern · v0.1")


# ═══════════════════════════════════════════════════════
# WHERE
# ═══════════════════════════════════════════════════════
filters, filter_params = [], []

if source != "All":
    filters.append("a.source_name = ?")
    filter_params.append(source)
if language != "All":
    filters.append("a.language = ?")
    filter_params.append(language)
if len(date_range) == 2:
    filters.append("a.publish_date::DATE >= ? AND a.publish_date::DATE <= ?")
    filter_params.extend([str(date_range[0]), str(date_range[1])])

where_clause = " AND ".join(filters) if filters else "1=1"


# ═══════════════════════════════════════════════════════
# WORD CLOUD
# ═══════════════════════════════════════════════════════
st.markdown("### Trending words")

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

    # Auto-détection : on garde le script majoritaire pour éviter le mélange
    arabic_total = sum(c for w, c in words_dict.items() if ARABIC_REGEX.search(w))
    latin_total  = sum(c for w, c in words_dict.items() if not ARABIC_REGEX.search(w))

    if arabic_total > latin_total:
        words_dict = {w: c for w, c in words_dict.items() if ARABIC_REGEX.search(w)}
        words_dict = reshape_arabic_dict(words_dict)
        font_path  = ARABIC_FONT
    else:
        words_dict = {w: c for w, c in words_dict.items() if not ARABIC_REGEX.search(w)}
        font_path  = LATIN_FONT

    if words_dict:
        wc = WordCloud(
            width=1200, height=500,
            background_color="white",
            max_words=max_words,
            colormap="cividis",
            font_path=font_path,
            prefer_horizontal=0.95,
            margin=8,
        )
        wc.generate_from_frequencies(words_dict)

        fig, ax = plt.subplots(figsize=(18, 7))
        ax.imshow(wc, interpolation="bilinear")
        ax.axis("off")
        fig.patch.set_facecolor("white")
        st.pyplot(fig)
    else:
        st.info("No words to display for this script.")
else:
    st.info("No data matches your filters.")


# ═══════════════════════════════════════════════════════
# TRENDS OVER TIME
# ═══════════════════════════════════════════════════════
st.markdown("### Trends over time")

top_words = list(words_dict.keys())[:200] if word_counts else []

if top_words:
    selected_words = st.multiselect(
        "Track specific words",
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
            SELECT d.date, d.word, d.count * 1.0 / t.total AS share
            FROM daily_counts d
            JOIN daily_totals t ON d.date = t.date
            ORDER BY d.date
        """, filter_params)

        if trend_data:
            df = pd.DataFrame(trend_data, columns=["Date", "Word", "Share"])
            fig = px.line(
                df, x="Date", y="Share", color="Word",
                markers=True, line_shape="spline",
            )
            fig.update_layout(
                height=450,
                margin=dict(l=20, r=20, t=20, b=20),
                plot_bgcolor="white",
                paper_bgcolor="white",
                xaxis=dict(gridcolor="#f3f4f6", title=""),
                yaxis=dict(gridcolor="#f3f4f6", title="Share of mentions",
                           tickformat=".1%"),
                legend=dict(orientation="h", y=-0.15, x=0),
                font=dict(family="Inter", size=12, color="#374151"),
            )
            fig.update_traces(line=dict(width=2.5))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No data for these words with current filters.")
    else:
        st.caption("Pick at least one word above.")
else:
    st.caption("Adjust filters to see available words.")