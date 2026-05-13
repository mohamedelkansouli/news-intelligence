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
    initial_sidebar_state="collapsed", # Masqué par défaut pour l'épure
)

# ==========================================
# PROFESSIONAL UI STYLING
# ==========================================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700&family=Playfair+Display:wght@700&display=swap');

    :root {
        --primary-color: #2563eb;
        --text-main: #0f172a;
        --text-muted: #64748b;
        --bg-light: #f8fafc;
        --border-color: #e2e8f0;
    }

    /* Global Overrides */
    .stApp { background-color: var(--bg-light); }
    html, body, [class*="css"] { 
        font-family: 'Plus Jakarta Sans', sans-serif; 
        color: var(--text-main);
    }

    /* Main Container */
    .block-container { padding: 2rem 5rem !important; }

    /* Header & Filter Bar */
    .header-container {
        text-align: left;
        margin-bottom: 1.5rem;
    }
    
    .header-container h1 {
        font-family: 'Playfair Display', serif !important;
        font-weight: 700 !important;
        font-size: 3.2rem !important;
        color: var(--text-main);
        margin: 0;
    }

    .header-container p {
        font-size: 1rem;
        color: var(--text-muted);
        margin-top: 0.2rem;
    }

    /* Horizontal Filter Bar Styling */
    div[data-testid="stHorizontalBlock"] {
        background: white;
        padding: 1.5rem;
        border-radius: 16px;
        border: 1px solid var(--border-color);
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
        margin-bottom: 2rem;
        align-items: end;
    }

    /* Section Cards */
    .content-card {
        background: #ffffff;
        padding: 2rem;
        border-radius: 16px;
        box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1);
        margin-bottom: 2rem;
        border: 1px solid var(--border-color);
    }

    h2 {
        font-weight: 700 !important;
        font-size: 1.3rem !important;
        color: var(--text-main);
        margin-bottom: 1.5rem !important;
        display: flex;
        align-items: center;
    }

    h2::before {
        content: "";
        width: 4px;
        height: 20px;
        background: var(--primary-color);
        margin-right: 12px;
        border-radius: 2px;
    }

    /* Form Elements focus */
    .stSelectbox:focus, .stDateInput:focus {
        border-color: var(--primary-color) !important;
    }
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

# ==========================================
# HEADER SECTION
# ==========================================
st.markdown("""
    <div class="header-container">
        <h1>The News Pattern</h1>
        <p>Global Media Intelligence & Trend Analysis Dashboard</p>
    </div>
""", unsafe_allow_html=True)

# ==========================================
# HORIZONTAL FILTERS (Anciennement Sidebar)
# ==========================================
# On crée 4 colonnes pour une disposition propre sous le titre
col1, col2, col3, col4 = st.columns([1.5, 1.2, 1.8, 1.5])

with col1:
    sources_raw  = run_query("SELECT DISTINCT source_name FROM articles ORDER BY source_name")
    sources_list = ["All"] + [s[0] for s in sources_raw if s[0]]
    source = st.selectbox("Source", sources_list)

with col2:
    languages_raw  = run_query("SELECT DISTINCT language FROM articles ORDER BY language")
    LANG_LABELS    = {"en": "English", "fr": "Français", "ar": "العربية"}
    languages_list = ["All"] + [l[0] for l in languages_raw if l[0]]
    default_lang = "en" if "en" in languages_list else "All"
    lang_index = languages_list.index(default_lang)
    
    language = st.selectbox(
        "Language",
        languages_list,
        index=lang_index,
        format_func=lambda x: "All" if x == "All" else LANG_LABELS.get(x, x),
    )

with col3:
    date_row = run_query("SELECT MIN(publish_date)::DATE, MAX(publish_date)::DATE FROM articles")
    min_date, max_date = date_row[0] if date_row else (None, None)
    date_range = st.date_input("Date range", value=[min_date, max_date]) if min_date else []

with col4:
    max_words = st.slider("Words count", 50, 300, 120)

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
st.markdown('<div class="content-card">', unsafe_allow_html=True)
st.markdown("## Trending keywords")

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
    arabic_total = sum(c for w, c in words_dict.items() if ARABIC_REGEX.search(w))
    latin_total  = sum(c for w, c in words_dict.items() if not ARABIC_REGEX.search(w))

    if arabic_total > latin_total:
        words_dict = {w: c for w, c in words_dict.items() if ARABIC_REGEX.search(w)}
        words_for_cloud = reshape_arabic_dict(words_dict) if words_dict else {}
        font_path = ARABIC_FONT
    else:
        words_dict = {w: c for w, c in words_dict.items() if not ARABIC_REGEX.search(w)}
        words_for_cloud = words_dict
        font_path = LATIN_FONT

    if words_for_cloud:
        wc = WordCloud(
            width=1200, height=400,
            background_color="white",
            max_words=max_words,
            colormap="Blues_r",
            font_path=font_path,
            prefer_horizontal=0.9,
        )
        wc.generate_from_frequencies(words_for_cloud)
        fig, ax = plt.subplots(figsize=(16, 5))
        ax.imshow(wc, interpolation="bilinear")
        ax.axis("off")
        st.pyplot(fig)
    else:
        st.info("No data available for the current selection.")
else:
    st.info("No data matches selected filters.")
st.markdown('</div>', unsafe_allow_html=True)

# ==========================================
# TREND ANALYSIS SECTION
# ==========================================
st.markdown('<div class="content-card">', unsafe_allow_html=True)
st.markdown("## Temporal Trends")

top_words = list(words_dict.keys())[:200] if word_counts else []

if top_words:
    if "trends_words" not in st.session_state:
        st.session_state.trends_words = [top_words[0]] if top_words else []
    else:
        st.session_state.trends_words = [w for w in st.session_state.trends_words if w in top_words]
        if not st.session_state.trends_words and top_words:
            st.session_state.trends_words = [top_words[0]]

    selected_words = st.multiselect(
        "Track keyword frequency over time",
        options=top_words,
        key="trends_words"
    )

    if selected_words:
        escaped = ", ".join(f"'{w.replace(chr(39), chr(39)+chr(39))}'" for w in selected_words)
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
                WHERE word IN ({escaped})
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
                color_discrete_sequence=px.colors.qualitative.Prism
            )
            fig.update_layout(
                height=400,
                margin=dict(l=0, r=0, t=10, b=0),
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                xaxis=dict(showgrid=True, gridcolor="#f1f5f9", title=""),
                yaxis=dict(showgrid=True, gridcolor="#f1f5f9", title="Frequency Share", tickformat=".1%"),
                legend=dict(orientation="h", y=-0.2, x=0),
                font=dict(family="Plus Jakarta Sans", size=12),
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Insufficient data for the selected keywords.")
    else:
        st.caption("Select keywords to visualize trends.")
else:
    st.caption("Adjust filters to refresh available keywords.")
st.markdown('</div>', unsafe_allow_html=True)