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

# ==========================================
# PAGE CONFIGURATION
# ==========================================
st.set_page_config(
    page_title="The News Pattern",
    page_icon="◐",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ==========================================
# FINANCIAL TIMES STYLE + HEADER REMOVAL
# ==========================================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700&family=Playfair+Display:wght@700&display=swap');

    :root {
        --primary-color: #990f3d; 
        --text-main: #33302e;    
        --text-muted: #6b5a50;   
        --bg-paper: #fff1e5;     
        --accent-line: #4d2d18;  
    }

    /* SUPPRESSION DU HEADER (Boutons Share, GitHub, etc.) */
    header {visibility: hidden !important;}
    footer {visibility: hidden !important;}
    #MainMenu {visibility: hidden !important;}

    /* Fond de l'application */
    .stApp { 
        background-color: var(--bg-paper); 
    }

    /* Texte global */
    html, body, [class*="css"], .stMarkdown, p, label { 
        color: var(--text-main) !important;
        font-family: 'Plus Jakarta Sans', sans-serif; 
    }

    .block-container { 
        padding: 1rem !important; 
    }
    @media (min-width: 768px) {
        .block-container { padding: 3rem 5rem !important; }
    }

    /* Header Titre */
    .header-container h1 {
        font-family: 'Playfair Display', serif !important;
        font-weight: 700 !important;
        color: var(--text-main);
        margin: 0;
    }

    @media (max-width: 768px) {
        .header-container h1 { font-size: 2.2rem !important; }
    }
    @media (min-width: 769px) {
        .header-container h1 { font-size: 3.8rem !important; }
    }

    /* Filtres */
    div[data-testid="stHorizontalBlock"] {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
    }

    .stSelectbox div[data-baseweb="select"] {
        background-color: rgba(255, 255, 255, 0.4) !important;
        border-radius: 4px !important;
    }

    /* Titres de sections */
    h2 {
        font-family: 'Playfair Display', serif !important;
        font-weight: 700 !important;
        font-size: 1.5rem !important;
        color: var(--text-main);
        border: none !important;
        margin-top: 2rem !important;
    }

    h2::before {
        content: "";
        width: 40px;
        height: 3px;
        background: var(--accent-line);
        margin-right: 15px;
    }

    hr { display: none !important; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# CORE API & DATA FUNCTIONS (Inchangé)
# ==========================================
API_URL   = os.environ.get("API_URL")   or st.secrets.get("API_URL")
API_TOKEN = os.environ.get("API_TOKEN") or st.secrets.get("API_TOKEN")

@st.cache_data(ttl=300)
def run_query(sql, params=None):
    resp = requests.post(
        f"{API_URL}/query",
        json={"sql": sql, "params": params or []},
        headers={"Authorization": f"Bearer {API_TOKEN}"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["rows"]

# ==========================================
# FONT & LANGUAGE HELPERS (Inchangé)
# ==========================================
ARABIC_REGEX = re.compile(r"[\u0600-\u06FF]")
def find_font(candidates):
    for path in candidates:
        if os.path.exists(path): return path
    return None

ARABIC_FONT = find_font(["/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf"])
LATIN_FONT = find_font(["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"])

def reshape_arabic_dict(words_dict):
    return {get_display(arabic_reshaper.reshape(w)): c for w, c in words_dict.items()}

# ==========================================
# HEADER SECTION
# ==========================================
st.markdown("""
    <div class="header-container">
        <h1>The News Pattern</h1>
        <p style="color:#6b5a50; font-style: italic; margin-top:5px;">Global Media Intelligence & Trend Analysis Dashboard</p>
    </div>
""", unsafe_allow_html=True)

# ==========================================
# HORIZONTAL FILTERS
# ==========================================
c1, c2, c3, c4 = st.columns([1, 1, 1.2, 1])

with c1:
    sources_raw  = run_query("SELECT DISTINCT source_name FROM articles ORDER BY source_name")
    sources_list = ["All"] + [s[0] for s in sources_raw if s[0]]
    source = st.selectbox("Source", sources_list)

with c2:
    languages_raw  = run_query("SELECT DISTINCT language FROM articles ORDER BY language")
    LANG_LABELS    = {"en": "English", "fr": "Français", "ar": "العربية"}
    languages_list = ["All"] + [l[0] for l in languages_raw if l[0]]
    language = st.selectbox("Language", languages_list, index=languages_list.index("en") if "en" in languages_list else 0, format_func=lambda x: LANG_LABELS.get(x, x))

with c3:
    date_row = run_query("SELECT MIN(publish_date)::DATE, MAX(publish_date)::DATE FROM articles")
    min_date, max_date = date_row[0] if date_row else (None, None)
    date_range = st.date_input("Period", value=[min_date, max_date]) if min_date else []

with c4:
    max_words = st.slider("Limit", 50, 300, 120)

# ==========================================
# DATA FILTERING LOGIC (Inchangé)
# ==========================================
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

# ==========================================
# WORD CLOUD VISUALIZATION
# ==========================================
st.markdown("## Trending keywords")

word_counts = run_query(f"""
    SELECT w.word, COUNT(*) as count FROM article_words w
    JOIN articles a ON w.article_id = a.article_id
    WHERE {where_clause} GROUP BY w.word ORDER BY count DESC
""", filter_params)

if word_counts:
    words_dict = {w: c for w, c in word_counts}
    arabic_total = sum(c for w, c in words_dict.items() if ARABIC_REGEX.search(w))
    latin_total  = sum(c for w, c in words_dict.items() if not ARABIC_REGEX.search(w))

    if arabic_total > latin_total:
        words_dict = {w: c for w, c in words_dict.items() if ARABIC_REGEX.search(w)}
        words_for_cloud = reshape_arabic_dict(words_dict)
        font_path = ARABIC_FONT
    else:
        words_dict = {w: c for w, c in words_dict.items() if not ARABIC_REGEX.search(w)}
        words_for_cloud = words_dict
        font_path = LATIN_FONT

    if words_for_cloud:
        wc = WordCloud(width=1200, height=500, background_color="#fff1e5", max_words=max_words, colormap="Dark2", font_path=font_path)
        wc.generate_from_frequencies(words_for_cloud)
        fig, ax = plt.subplots(figsize=(16, 7), facecolor='#fff1e5')
        ax.imshow(wc, interpolation="bilinear")
        ax.axis("off")
        st.pyplot(fig)

# ==========================================
# TREND ANALYSIS SECTION
# ==========================================
st.markdown("## Temporal Trends")

top_words = list(words_dict.keys())[:200] if word_counts else []
if top_words:
    selected_words = st.multiselect("Select keywords", options=top_words, default=[top_words[0]] if top_words else [], key="trends_words")

    if selected_words:
        escaped = ", ".join(f"'{w.replace(chr(39), chr(39)+chr(39))}'" for w in selected_words)
        trend_data = run_query(f"""
            WITH filtered AS (SELECT a.publish_date::DATE as date, w.word FROM article_words w JOIN articles a ON w.article_id = a.article_id WHERE {where_clause}),
            daily_counts AS (SELECT date, word, COUNT(*) as count FROM filtered WHERE word IN ({escaped}) GROUP BY date, word),
            daily_totals AS (SELECT date, COUNT(*) as total FROM filtered GROUP BY date)
            SELECT d.date, d.word, d.count * 1.0 / t.total AS share FROM daily_counts d JOIN daily_totals t ON d.date = t.date ORDER BY d.date
        """, filter_params)

        if trend_data:
            df = pd.DataFrame(trend_data, columns=["Date", "Word", "Share"])
            fig = px.line(df, x="Date", y="Share", color="Word", markers=True, line_shape="spline", color_discrete_sequence=px.colors.qualitative.Bold)
            fig.update_layout(
                height=450, 
                margin=dict(l=0, r=0, t=10, b=0), 
                plot_bgcolor="rgba(0,0,0,0)", 
                paper_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#33302e"),
                xaxis=dict(gridcolor="#e5d5c5"),
                yaxis=dict(gridcolor="#e5d5c5")
            )
            st.plotly_chart(fig, use_container_width=True)