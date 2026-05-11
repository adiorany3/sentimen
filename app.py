import os
import re
import sqlite3
import time
from html import unescape
from datetime import datetime
from urllib.parse import quote_plus

import feedparser
import pandas as pd
import requests
import streamlit as st
from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification


# =========================
# KONFIGURASI DASAR
# =========================

DB_PATH = "data/berita_sentimen.db"
MODEL_NAME = "mdhugol/indonesia-bert-sentiment-classification"

LABEL_MAP = {
    "LABEL_0": "positive",
    "LABEL_1": "neutral",
    "LABEL_2": "negative",
    "positive": "positive",
    "neutral": "neutral",
    "negative": "negative",
}

LABEL_ID = {
    "positive": "Positif",
    "neutral": "Netral",
    "negative": "Negatif",
}

os.makedirs("data", exist_ok=True)


# =========================
# DATABASE
# =========================

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS berita_sentimen (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tema TEXT NOT NULL,
            sumber TEXT,
            judul TEXT,
            ringkasan TEXT,
            link TEXT,
            tanggal_publikasi TEXT,
            sentimen TEXT,
            skor REAL,
            created_at TEXT,
            UNIQUE(tema, link)
        )
    """)

    conn.commit()
    conn.close()


def save_to_db(df: pd.DataFrame):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    for _, row in df.iterrows():
        cursor.execute("""
            INSERT OR REPLACE INTO berita_sentimen
            (
                tema,
                sumber,
                judul,
                ringkasan,
                link,
                tanggal_publikasi,
                sentimen,
                skor,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            row.get("tema", ""),
            row.get("sumber", ""),
            row.get("judul", ""),
            row.get("ringkasan", ""),
            row.get("link", ""),
            row.get("tanggal_publikasi", ""),
            row.get("sentimen", ""),
            float(row.get("skor", 0)),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ))

    conn.commit()
    conn.close()


def load_history():
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query("""
            SELECT
                tema,
                sumber,
                judul,
                ringkasan,
                link,
                tanggal_publikasi,
                sentimen,
                skor,
                created_at
            FROM berita_sentimen
            ORDER BY created_at DESC
        """, conn)
    except Exception:
        df = pd.DataFrame()
    finally:
        conn.close()

    return df


# =========================
# PREPROCESSING
# =========================

def clean_text(text):
    text = str(text or "")
    text = unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_date(entry):
    published = entry.get("published_parsed") or entry.get("updated_parsed")

    if published:
        try:
            return datetime(*published[:6]).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return ""

    return ""


def get_source_name(entry, fallback_source):
    source = entry.get("source")

    if isinstance(source, dict):
        return source.get("title", fallback_source)

    return fallback_source


def build_google_news_rss(keyword):
    query = quote_plus(keyword)
    return f"https://news.google.com/rss/search?q={query}&hl=id&gl=ID&ceid=ID:id"


def is_relevant_to_theme(title, summary, theme):
    text = f"{title} {summary}".lower()
    keywords = [x.lower() for x in re.findall(r"\w+", theme) if len(x) >= 3]

    if not keywords:
        return True

    return any(keyword in text for keyword in keywords)


# =========================
# AMBIL BERITA
# =========================

def get_feed_with_retry(feed_url, max_retries=3, timeout=15):
    """
    Mengambil RSS dengan cara yang lebih aman.
    Beberapa server RSS akan menutup koneksi jika request tidak memiliki User-Agent
    atau jika koneksi terlalu lama. Fungsi ini membuat aplikasi tidak langsung crash.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        ),
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    }

    last_error = None

    for attempt in range(max_retries):
        try:
            response = requests.get(
                feed_url,
                headers=headers,
                timeout=timeout,
                allow_redirects=True,
            )
            response.raise_for_status()
            return feedparser.parse(response.content), None

        except Exception as error:
            last_error = error
            if attempt < max_retries - 1:
                time.sleep(1.5)

    return None, str(last_error)


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_rss(feed_url, theme, source_name, max_items=20, filter_by_theme=True):
    feed, error = get_feed_with_retry(feed_url)

    if error or feed is None:
        return [], f"Gagal membaca RSS {source_name}: {error}"

    rows = []

    for entry in feed.entries:
        title = clean_text(entry.get("title", ""))
        summary = clean_text(entry.get("summary", ""))
        link = entry.get("link", "")
        published = parse_date(entry)
        actual_source = get_source_name(entry, source_name)

        if not title or not link:
            continue

        if filter_by_theme and not is_relevant_to_theme(title, summary, theme):
            continue

        rows.append({
            "tema": theme,
            "sumber": actual_source,
            "judul": title,
            "ringkasan": summary,
            "link": link,
            "tanggal_publikasi": published,
        })

        if len(rows) >= max_items:
            break

    return rows, None


def fetch_news_by_theme(theme, max_items, custom_feeds):
    rows = []
    errors = []

    google_rss = build_google_news_rss(theme)
    google_rows, google_error = fetch_rss(
        feed_url=google_rss,
        theme=theme,
        source_name="Google News",
        max_items=max_items,
        filter_by_theme=False
    )
    rows.extend(google_rows)

    if google_error:
        errors.append(google_error)

    for source_name, feed_url in custom_feeds.items():
        source_rows, source_error = fetch_rss(
            feed_url=feed_url,
            theme=theme,
            source_name=source_name,
            max_items=max_items,
            filter_by_theme=True
        )
        rows.extend(source_rows)

        if source_error:
            errors.append(source_error)

    df = pd.DataFrame(rows)

    if df.empty:
        return df, errors

    df = df.drop_duplicates(subset=["tema", "link"])
    df = df.head(max_items)

    return df, errors


# =========================
# MODEL SENTIMEN
# =========================

@st.cache_resource
def load_sentiment_model():
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME)

    sentiment_pipeline = pipeline(
        "sentiment-analysis",
        model=model,
        tokenizer=tokenizer
    )

    return sentiment_pipeline


def analyze_sentiment_batch(texts, batch_size=8):
    model = load_sentiment_model()
    results = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]

        output = model(
            batch,
            truncation=True,
            max_length=256
        )

        results.extend(output)

    return results


def add_sentiment(df):
    if df.empty:
        return df

    texts = (
        df["judul"].fillna("") + ". " + df["ringkasan"].fillna("")
    ).tolist()

    results = analyze_sentiment_batch(texts)

    sentiments = []
    scores = []

    for result in results:
        raw_label = result.get("label", "")
        label = LABEL_MAP.get(raw_label, raw_label.lower())

        sentiments.append(label)
        scores.append(float(result.get("score", 0)))

    df["sentimen"] = sentiments
    df["skor"] = scores

    return df


# =========================
# STREAMLIT UI
# =========================

st.set_page_config(
    page_title="Sistem Analisis Sentimen Berita",
    page_icon="📰",
    layout="wide"
)

init_db()

st.title("📰 Sistem Analisis Sentimen Berita Berdasarkan Tema")
st.caption("Input tema, ambil berita dari beberapa sumber, analisis sentimen, lalu kelola hasil dalam dashboard.")

with st.sidebar:
    st.header("Pengaturan")

    max_items = st.number_input(
        "Maksimal berita per tema",
        min_value=5,
        max_value=100,
        value=20,
        step=5
    )

    st.subheader("RSS Tambahan")
    st.write("Masukkan RSS tambahan, satu URL per baris.")

    default_rss = """ANTARA Terkini|https://www.antaranews.com/rss/terkini.xml
ANTARA Top News|https://www.antaranews.com/rss/top-news.xml
ANTARA Politik|https://www.antaranews.com/rss/politik.xml
ANTARA Hukum|https://www.antaranews.com/rss/hukum.xml
ANTARA Ekonomi|https://www.antaranews.com/rss/ekonomi.xml
ANTARA Dunia|https://www.antaranews.com/rss/dunia.xml
ANTARA Olahraga|https://www.antaranews.com/rss/olahraga.xml
ANTARA Teknologi|https://www.antaranews.com/rss/tekno.xml
CNN Indonesia Nasional|https://www.cnnindonesia.com/nasional/rss
CNN Indonesia Ekonomi|https://www.cnnindonesia.com/ekonomi/rss
CNN Indonesia Teknologi|https://www.cnnindonesia.com/teknologi/rss
Tempo Nasional|https://rss.tempo.co/nasional
Tempo Bisnis|https://rss.tempo.co/bisnis
CNBC Indonesia News|https://www.cnbcindonesia.com/news/rss
CNBC Indonesia Market|https://www.cnbcindonesia.com/market/rss
Liputan6 News|https://feed.liputan6.com/rss/news
Suara News|https://www.suara.com/rss/news
Republika Nasional|https://www.republika.co.id/rss/nasional"""

    custom_rss_text = st.text_area(
        "Format: Nama Sumber|URL RSS",
        value=default_rss,
        height=360,
        help="Daftar ini sudah berisi lebih dari 10 RSS. Anda tetap bisa menambah, menghapus, atau mengganti URL sesuai kebutuhan."
    )

    custom_feeds = {}

    for line in custom_rss_text.splitlines():
        line = line.strip()

        if not line:
            continue

        if "|" in line:
            name, url = line.split("|", 1)
            name = name.strip()
            url = url.strip()

            if name and url:
                custom_feeds[name] = url

    st.caption(f"Total sumber RSS aktif: {len(custom_feeds)} sumber")

    st.divider()

    if st.button("Hapus seluruh data tersimpan"):
        conn = sqlite3.connect(DB_PATH)
        conn.execute("DELETE FROM berita_sentimen")
        conn.commit()
        conn.close()
        st.success("Data berhasil dihapus.")
        st.rerun()


# =========================
# INPUT TEMA
# =========================

st.subheader("1. Input Tema")

col_input_1, col_input_2 = st.columns([1, 1])

with col_input_1:
    manual_theme_text = st.text_area(
        "Tulis tema secara manual, satu tema per baris",
        value="BPJS Kesehatan\nIKN\nPemilu",
        height=160
    )

with col_input_2:
    uploaded_file = st.file_uploader(
        "Atau upload file CSV/Excel yang memiliki kolom tema",
        type=["csv", "xlsx"]
    )

uploaded_themes = []

if uploaded_file is not None:
    try:
        if uploaded_file.name.endswith(".csv"):
            uploaded_df = pd.read_csv(uploaded_file)
        else:
            uploaded_df = pd.read_excel(uploaded_file)

        st.write("Preview file:")
        st.dataframe(uploaded_df.head(), use_container_width=True)

        selected_column = st.selectbox(
            "Pilih kolom yang berisi tema",
            uploaded_df.columns
        )

        uploaded_themes = (
            uploaded_df[selected_column]
            .dropna()
            .astype(str)
            .str.strip()
            .unique()
            .tolist()
        )

    except Exception as e:
        st.error(f"Gagal membaca file: {e}")


manual_themes = [
    theme.strip()
    for theme in manual_theme_text.splitlines()
    if theme.strip()
]

themes = sorted(set(manual_themes + uploaded_themes))

st.info(f"Jumlah tema yang akan dianalisis: {len(themes)}")


# =========================
# PROSES ANALISIS
# =========================

st.subheader("2. Ambil Berita dan Analisis Sentimen")

if st.button("Mulai Analisis", type="primary"):
    if not themes:
        st.warning("Masukkan minimal satu tema terlebih dahulu.")
    else:
        all_results = []
        progress = st.progress(0)

        for index, theme in enumerate(themes):
            st.write(f"Mengambil berita untuk tema: **{theme}**")

            news_df, rss_errors = fetch_news_by_theme(
                theme=theme,
                max_items=max_items,
                custom_feeds=custom_feeds
            )

            for rss_error in rss_errors:
                st.warning(rss_error)

            if not news_df.empty:
                analyzed_df = add_sentiment(news_df)
                all_results.append(analyzed_df)
            else:
                st.info(f"Tidak ada berita yang berhasil diambil untuk tema: {theme}")

            progress.progress((index + 1) / len(themes))

        if all_results:
            final_df = pd.concat(all_results, ignore_index=True)
            save_to_db(final_df)

            st.success(f"Analisis selesai. {len(final_df)} berita berhasil diproses.")
            st.dataframe(final_df, use_container_width=True)
        else:
            st.warning("Tidak ada berita yang berhasil ditemukan.")


# =========================
# DASHBOARD HASIL
# =========================

st.subheader("3. Dashboard Hasil Sentimen")

history_df = load_history()

if history_df.empty:
    st.info("Belum ada data tersimpan.")
else:
    filter_col_1, filter_col_2 = st.columns([1, 1])

    with filter_col_1:
        selected_themes = st.multiselect(
            "Filter tema",
            sorted(history_df["tema"].dropna().unique())
        )

    with filter_col_2:
        selected_sentiments = st.multiselect(
            "Filter sentimen",
            ["positive", "neutral", "negative"],
            format_func=lambda x: LABEL_ID.get(x, x)
        )

    filtered_df = history_df.copy()

    if selected_themes:
        filtered_df = filtered_df[filtered_df["tema"].isin(selected_themes)]

    if selected_sentiments:
        filtered_df = filtered_df[filtered_df["sentimen"].isin(selected_sentiments)]

    metric_1, metric_2, metric_3, metric_4 = st.columns(4)

    metric_1.metric("Total Berita", len(filtered_df))
    metric_2.metric("Tema", filtered_df["tema"].nunique())
    metric_3.metric("Sumber", filtered_df["sumber"].nunique())

    if len(filtered_df) > 0:
        dominant = filtered_df["sentimen"].value_counts().idxmax()
        metric_4.metric("Sentimen Dominan", LABEL_ID.get(dominant, dominant))
    else:
        metric_4.metric("Sentimen Dominan", "-")

    st.write("Distribusi Sentimen")

    sentiment_count = (
        filtered_df["sentimen"]
        .value_counts()
        .rename(index=LABEL_ID)
    )

    st.bar_chart(sentiment_count)

    st.write("Distribusi Sentimen per Tema")

    if not filtered_df.empty:
        pivot_df = pd.crosstab(
            filtered_df["tema"],
            filtered_df["sentimen"]
        ).rename(columns=LABEL_ID)

        st.dataframe(pivot_df, use_container_width=True)

    st.write("Data Berita")

    display_df = filtered_df.copy()
    display_df["sentimen"] = display_df["sentimen"].map(LABEL_ID)

    st.dataframe(
        display_df[
            [
                "tema",
                "sumber",
                "judul",
                "ringkasan",
                "tanggal_publikasi",
                "sentimen",
                "skor",
                "link",
                "created_at"
            ]
        ],
        use_container_width=True
    )

    csv_data = filtered_df.to_csv(index=False).encode("utf-8")

    st.download_button(
        label="Download Hasil CSV",
        data=csv_data,
        file_name="hasil_sentimen_berita.csv",
        mime="text/csv"
    )
