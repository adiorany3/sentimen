import os
import re
import sqlite3
import time
from html import unescape
from datetime import datetime
from urllib.parse import quote_plus, urlparse, parse_qs

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

def get_connection():
    return sqlite3.connect(DB_PATH)


def init_db():
    conn = get_connection()
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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS komentar_sentimen (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tema TEXT,
            sumber_berita TEXT,
            judul_berita TEXT,
            link_berita TEXT,
            platform TEXT,
            social_url TEXT,
            penulis TEXT,
            komentar TEXT,
            like_count INTEGER,
            tanggal_komentar TEXT,
            sentimen_komentar TEXT,
            skor_komentar REAL,
            created_at TEXT,
            UNIQUE(link_berita, platform, social_url, komentar)
        )
    """)

    conn.commit()
    conn.close()


def save_to_db(df: pd.DataFrame):
    conn = get_connection()
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


def save_comments_to_db(df: pd.DataFrame):
    conn = get_connection()
    cursor = conn.cursor()

    for _, row in df.iterrows():
        cursor.execute("""
            INSERT OR REPLACE INTO komentar_sentimen
            (
                tema,
                sumber_berita,
                judul_berita,
                link_berita,
                platform,
                social_url,
                penulis,
                komentar,
                like_count,
                tanggal_komentar,
                sentimen_komentar,
                skor_komentar,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            row.get("tema", ""),
            row.get("sumber_berita", ""),
            row.get("judul_berita", ""),
            row.get("link_berita", ""),
            row.get("platform", ""),
            row.get("social_url", ""),
            row.get("penulis", ""),
            row.get("komentar", ""),
            int(row.get("like_count", 0) or 0),
            row.get("tanggal_komentar", ""),
            row.get("sentimen_komentar", ""),
            float(row.get("skor_komentar", 0) or 0),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ))

    conn.commit()
    conn.close()


def load_history():
    conn = get_connection()
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


def load_comments_history():
    conn = get_connection()
    try:
        df = pd.read_sql_query("""
            SELECT
                tema,
                sumber_berita,
                judul_berita,
                link_berita,
                platform,
                social_url,
                penulis,
                komentar,
                like_count,
                tanggal_komentar,
                sentimen_komentar,
                skor_komentar,
                created_at
            FROM komentar_sentimen
            ORDER BY created_at DESC
        """, conn)
    except Exception:
        df = pd.DataFrame()
    finally:
        conn.close()

    return df


def clear_table(table_name):
    conn = get_connection()
    conn.execute(f"DELETE FROM {table_name}")
    conn.commit()
    conn.close()


# =========================
# PREPROCESSING
# =========================

def clean_text(text):
    text = str(text or "")
    text = unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"https?://\S+", " ", text)
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


def format_unix_date(timestamp_value):
    if not timestamp_value:
        return ""

    try:
        return datetime.fromtimestamp(float(timestamp_value)).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
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


def make_news_query(row):
    title = clean_text(row.get("judul", ""))
    theme = clean_text(row.get("tema", ""))
    query = f"{title} {theme}".strip()
    return query[:180]


# =========================
# AMBIL BERITA RSS
# =========================

def get_feed_with_retry(feed_url, max_retries=3, timeout=15):
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
# SOSIAL MEDIA: YOUTUBE DAN REDDIT
# =========================

def request_json(url, params=None, headers=None, timeout=20, max_retries=2):
    default_headers = {
        "User-Agent": "sentimen-berita-streamlit/1.0 by inikansatuin",
        "Accept": "application/json, text/plain, */*",
    }
    final_headers = default_headers | (headers or {})
    last_error = None

    for attempt in range(max_retries):
        try:
            response = requests.get(url, params=params, headers=final_headers, timeout=timeout)
            response.raise_for_status()
            return response.json(), None
        except Exception as error:
            last_error = error
            if attempt < max_retries - 1:
                time.sleep(1.2)

    return None, str(last_error)


def extract_youtube_video_id(url):
    if not url:
        return ""

    parsed = urlparse(url.strip())
    host = parsed.netloc.lower().replace("www.", "")

    if host in ["youtube.com", "m.youtube.com"]:
        query = parse_qs(parsed.query)
        if "v" in query:
            return query["v"][0]

        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 2 and parts[0] in ["shorts", "embed", "live"]:
            return parts[1]

    if host == "youtu.be":
        parts = [part for part in parsed.path.split("/") if part]
        if parts:
            return parts[0]

    if re.fullmatch(r"[A-Za-z0-9_-]{8,20}", url.strip()):
        return url.strip()

    return ""


@st.cache_data(ttl=1800, show_spinner=False)
def search_youtube_videos(query, api_key, max_videos=2):
    if not api_key:
        return [], "API key YouTube belum diisi."

    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "maxResults": min(max_videos, 10),
        "relevanceLanguage": "id",
        "regionCode": "ID",
        "key": api_key,
    }

    data, error = request_json(url, params=params)
    if error:
        return [], f"Gagal mencari video YouTube: {error}"

    videos = []
    for item in data.get("items", []):
        video_id = item.get("id", {}).get("videoId", "")
        snippet = item.get("snippet", {})
        if not video_id:
            continue

        videos.append({
            "video_id": video_id,
            "title": snippet.get("title", ""),
            "url": f"https://www.youtube.com/watch?v={video_id}",
        })

    return videos, None


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_youtube_comments(video_id, api_key, max_comments=30):
    if not api_key:
        return [], "API key YouTube belum diisi."

    if not video_id:
        return [], "Video ID YouTube tidak valid."

    comments = []
    next_page_token = None
    url = "https://www.googleapis.com/youtube/v3/commentThreads"

    while len(comments) < max_comments:
        params = {
            "part": "snippet",
            "videoId": video_id,
            "maxResults": min(100, max_comments - len(comments)),
            "textFormat": "plainText",
            "order": "relevance",
            "key": api_key,
        }

        if next_page_token:
            params["pageToken"] = next_page_token

        data, error = request_json(url, params=params)
        if error:
            return comments, f"Gagal mengambil komentar YouTube: {error}"

        for item in data.get("items", []):
            snippet = item.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
            comment_text = clean_text(snippet.get("textOriginal", ""))

            if not comment_text:
                continue

            comments.append({
                "platform": "YouTube",
                "social_url": f"https://www.youtube.com/watch?v={video_id}",
                "penulis": snippet.get("authorDisplayName", ""),
                "komentar": comment_text,
                "like_count": int(snippet.get("likeCount", 0) or 0),
                "tanggal_komentar": snippet.get("publishedAt", ""),
            })

            if len(comments) >= max_comments:
                break

        next_page_token = data.get("nextPageToken")
        if not next_page_token:
            break

    return comments, None


@st.cache_data(ttl=1800, show_spinner=False)
def search_reddit_posts(query, subreddit="", max_posts=3):
    if subreddit:
        url = f"https://www.reddit.com/r/{subreddit.strip().strip('/')}/search.json"
        params = {
            "q": query,
            "restrict_sr": "on",
            "sort": "new",
            "limit": min(max_posts, 10),
        }
    else:
        url = "https://www.reddit.com/search.json"
        params = {
            "q": query,
            "sort": "new",
            "limit": min(max_posts, 10),
        }

    data, error = request_json(url, params=params)
    if error:
        return [], f"Gagal mencari post Reddit: {error}"

    posts = []
    children = data.get("data", {}).get("children", [])

    for child in children:
        post = child.get("data", {})
        permalink = post.get("permalink", "")
        if not permalink:
            continue

        posts.append({
            "title": post.get("title", ""),
            "url": f"https://www.reddit.com{permalink}",
            "permalink": permalink,
        })

    return posts, None


def flatten_reddit_comments(children, max_comments):
    rows = []

    def walk(comment_children):
        for child in comment_children:
            if len(rows) >= max_comments:
                return

            if child.get("kind") != "t1":
                continue

            data = child.get("data", {})
            body = clean_text(data.get("body", ""))

            if body and body not in ["[deleted]", "[removed]"]:
                rows.append({
                    "platform": "Reddit",
                    "social_url": data.get("permalink", ""),
                    "penulis": data.get("author", ""),
                    "komentar": body,
                    "like_count": int(data.get("ups", 0) or 0),
                    "tanggal_komentar": format_unix_date(data.get("created_utc")),
                })

            replies = data.get("replies")
            if isinstance(replies, dict):
                reply_children = replies.get("data", {}).get("children", [])
                walk(reply_children)

    walk(children)
    return rows


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_reddit_comments_from_post(post_url, max_comments=30):
    if not post_url:
        return [], "URL Reddit kosong."

    url = post_url.rstrip("/") + ".json"
    data, error = request_json(url, params={"limit": max_comments})

    if error:
        return [], f"Gagal mengambil komentar Reddit: {error}"

    if not isinstance(data, list) or len(data) < 2:
        return [], "Format respons Reddit tidak sesuai."

    children = data[1].get("data", {}).get("children", [])
    rows = flatten_reddit_comments(children, max_comments=max_comments)

    for row in rows:
        if row.get("social_url", "").startswith("/"):
            row["social_url"] = f"https://www.reddit.com{row['social_url']}"

    return rows, None


def build_comment_df(comment_rows, news_row):
    df = pd.DataFrame(comment_rows)

    if df.empty:
        return df

    df["tema"] = news_row.get("tema", "")
    df["sumber_berita"] = news_row.get("sumber", "")
    df["judul_berita"] = news_row.get("judul", "")
    df["link_berita"] = news_row.get("link", "")

    ordered_columns = [
        "tema",
        "sumber_berita",
        "judul_berita",
        "link_berita",
        "platform",
        "social_url",
        "penulis",
        "komentar",
        "like_count",
        "tanggal_komentar",
    ]

    return df[ordered_columns]


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


def normalize_sentiment_results(results):
    sentiments = []
    scores = []

    for result in results:
        raw_label = result.get("label", "")
        label = LABEL_MAP.get(raw_label, raw_label.lower())
        sentiments.append(label)
        scores.append(float(result.get("score", 0)))

    return sentiments, scores


def add_sentiment(df):
    if df.empty:
        return df

    texts = (
        df["judul"].fillna("") + ". " + df["ringkasan"].fillna("")
    ).tolist()

    results = analyze_sentiment_batch(texts)
    sentiments, scores = normalize_sentiment_results(results)

    df["sentimen"] = sentiments
    df["skor"] = scores

    return df


def add_comment_sentiment(df):
    if df.empty:
        return df

    texts = df["komentar"].fillna("").astype(str).tolist()
    results = analyze_sentiment_batch(texts)
    sentiments, scores = normalize_sentiment_results(results)

    df["sentimen_komentar"] = sentiments
    df["skor_komentar"] = scores

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

st.title("📰 Sistem Analisis Sentimen Berita dan Komentar Sosial Media")
st.caption("Input tema, ambil berita dari RSS, analisis sentimen berita, lalu ambil komentar sosial media untuk mengetahui respons publik.")

with st.sidebar:
    st.header("Pengaturan Berita")

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
Republika Nasional|https://www.republika.co.id/rss/nasional"""

    custom_rss_text = st.text_area(
        "Format: Nama Sumber|URL RSS",
        value=default_rss,
        height=300,
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
    st.header("Pengaturan Sosial Media")

    enable_youtube = st.checkbox("Aktifkan YouTube", value=True)
    youtube_api_key = st.text_input(
        "YouTube Data API Key",
        type="password",
        help="Dipakai untuk mencari video terkait berita dan membaca komentar YouTube. Kosongkan jika tidak digunakan."
    )

    enable_reddit = st.checkbox("Aktifkan Reddit publik", value=False)
    reddit_subreddit = st.text_input(
        "Subreddit opsional",
        value="",
        help="Contoh: indonesia. Kosongkan untuk pencarian Reddit global."
    )

    max_social_news = st.number_input(
        "Maksimal berita yang dianalisis komentar",
        min_value=1,
        max_value=10,
        value=3,
        step=1
    )

    max_social_posts = st.number_input(
        "Maksimal video/post per berita",
        min_value=1,
        max_value=5,
        value=2,
        step=1
    )

    max_comments_per_post = st.number_input(
        "Maksimal komentar per video/post",
        min_value=5,
        max_value=100,
        value=25,
        step=5
    )

    st.divider()
    st.header("Pengelolaan Data")

    if st.button("Hapus data berita tersimpan"):
        clear_table("berita_sentimen")
        st.success("Data berita berhasil dihapus.")
        st.rerun()

    if st.button("Hapus data komentar tersimpan"):
        clear_table("komentar_sentimen")
        st.success("Data komentar berhasil dihapus.")
        st.rerun()


# =========================
# TAB APLIKASI
# =========================

tab_berita, tab_sosmed, tab_dashboard_berita, tab_dashboard_komentar = st.tabs([
    "1. Analisis Berita",
    "2. Analisis Komentar Sosial Media",
    "3. Dashboard Berita",
    "4. Dashboard Komentar",
])


# =========================
# TAB 1: INPUT DAN ANALISIS BERITA
# =========================

with tab_berita:
    st.subheader("Input Tema")

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

    st.subheader("Ambil Berita dan Analisis Sentimen")

    if st.button("Mulai Analisis Berita", type="primary"):
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
# TAB 2: ANALISIS KOMENTAR SOSIAL MEDIA
# =========================

with tab_sosmed:
    st.subheader("Ambil Komentar Berdasarkan Berita Tersimpan")

    history_df_for_social = load_history()

    if history_df_for_social.empty:
        st.info("Belum ada berita tersimpan. Jalankan analisis berita terlebih dahulu.")
    else:
        filter_social_col_1, filter_social_col_2 = st.columns([1, 1])

        with filter_social_col_1:
            social_theme_filter = st.multiselect(
                "Filter tema berita",
                sorted(history_df_for_social["tema"].dropna().unique()),
                key="social_theme_filter"
            )

        with filter_social_col_2:
            social_source_filter = st.multiselect(
                "Filter sumber berita",
                sorted(history_df_for_social["sumber"].dropna().unique()),
                key="social_source_filter"
            )

        social_news_df = history_df_for_social.copy()

        if social_theme_filter:
            social_news_df = social_news_df[social_news_df["tema"].isin(social_theme_filter)]

        if social_source_filter:
            social_news_df = social_news_df[social_news_df["sumber"].isin(social_source_filter)]

        social_news_df = social_news_df.head(50).reset_index(drop=True)

        news_options = {
            f"{idx + 1}. [{row['tema']}] {row['judul'][:120]}": idx
            for idx, row in social_news_df.iterrows()
        }

        selected_news_labels = st.multiselect(
            "Pilih berita yang ingin dicari komentarnya",
            list(news_options.keys()),
            default=list(news_options.keys())[: min(max_social_news, len(news_options))]
        )

        selected_news_indices = [news_options[label] for label in selected_news_labels]

        st.caption(
            "YouTube membutuhkan API key. Reddit dibuat nonaktif secara default karena akses JSON publik sering diblokir 403 oleh hosting tertentu. "
            "Jika ingin mencoba Reddit, aktifkan checkbox Reddit di sidebar. Jika gagal, gunakan input komentar manual di bagian bawah."
        )

        if st.button("Ambil & Analisis Komentar Sosial Media", type="primary"):
            if not selected_news_indices:
                st.warning("Pilih minimal satu berita terlebih dahulu.")
            else:
                all_comment_results = []
                progress = st.progress(0)

                limited_indices = selected_news_indices[:max_social_news]

                for progress_index, row_index in enumerate(limited_indices):
                    news_row = social_news_df.loc[row_index].to_dict()
                    query = make_news_query(news_row)
                    st.write(f"Mencari komentar untuk berita: **{news_row.get('judul', '')[:120]}**")

                    collected_comments = []

                    if enable_youtube:
                        if youtube_api_key:
                            videos, youtube_search_error = search_youtube_videos(
                                query=query,
                                api_key=youtube_api_key,
                                max_videos=int(max_social_posts)
                            )

                            if youtube_search_error:
                                st.warning(youtube_search_error)

                            for video in videos:
                                comments, youtube_comment_error = fetch_youtube_comments(
                                    video_id=video.get("video_id", ""),
                                    api_key=youtube_api_key,
                                    max_comments=int(max_comments_per_post)
                                )
                                collected_comments.extend(comments)

                                if youtube_comment_error:
                                    st.warning(youtube_comment_error)
                        else:
                            st.info("YouTube aktif, tetapi API key belum diisi. YouTube dilewati.")

                    if enable_reddit:
                        posts, reddit_search_error = search_reddit_posts(
                            query=query,
                            subreddit=reddit_subreddit,
                            max_posts=int(max_social_posts)
                        )

                        if reddit_search_error:
                            st.warning(reddit_search_error)

                        for post in posts:
                            comments, reddit_comment_error = fetch_reddit_comments_from_post(
                                post_url=post.get("url", ""),
                                max_comments=int(max_comments_per_post)
                            )
                            collected_comments.extend(comments)

                            if reddit_comment_error:
                                st.warning(reddit_comment_error)

                    comment_df = build_comment_df(collected_comments, news_row)

                    if not comment_df.empty:
                        comment_df = comment_df.drop_duplicates(subset=["platform", "social_url", "komentar"])
                        comment_df = add_comment_sentiment(comment_df)
                        save_comments_to_db(comment_df)
                        all_comment_results.append(comment_df)
                        st.success(f"{len(comment_df)} komentar berhasil dianalisis untuk berita ini.")
                    else:
                        st.info("Tidak ada komentar yang berhasil diambil untuk berita ini.")

                    progress.progress((progress_index + 1) / len(limited_indices))

                if all_comment_results:
                    final_comment_df = pd.concat(all_comment_results, ignore_index=True)
                    st.success(f"Total {len(final_comment_df)} komentar berhasil dianalisis.")
                    st.dataframe(final_comment_df, use_container_width=True)
                else:
                    st.warning("Belum ada komentar yang berhasil dianalisis.")

    st.divider()
    st.subheader("Input Komentar Manual")
    st.write("Gunakan bagian ini untuk komentar dari Instagram, TikTok, X/Twitter, Facebook, atau platform lain yang Anda salin secara manual.")

    manual_col_1, manual_col_2 = st.columns([1, 1])

    with manual_col_1:
        manual_platform = st.selectbox(
            "Platform komentar manual",
            ["Instagram", "TikTok", "X/Twitter", "Facebook", "YouTube", "Reddit", "Lainnya"]
        )
        manual_social_url = st.text_input("URL postingan sosial media", value="")
        manual_theme = st.text_input("Tema komentar manual", value="")

    with manual_col_2:
        manual_news_title = st.text_input("Judul berita terkait", value="")
        manual_news_source = st.text_input("Sumber berita terkait", value="")
        manual_news_link = st.text_input("Link berita terkait", value="")

    manual_comments_text = st.text_area(
        "Masukkan komentar, satu komentar per baris",
        height=180,
        placeholder="Contoh:\nPelayanannya makin baik.\nSaya masih kecewa dengan kebijakan ini.\nBeritanya biasa saja."
    )

    if st.button("Analisis Komentar Manual"):
        manual_comments = [clean_text(line) for line in manual_comments_text.splitlines() if clean_text(line)]

        if not manual_comments:
            st.warning("Masukkan minimal satu komentar.")
        else:
            manual_rows = []

            for comment in manual_comments:
                manual_rows.append({
                    "tema": manual_theme,
                    "sumber_berita": manual_news_source,
                    "judul_berita": manual_news_title,
                    "link_berita": manual_news_link or manual_social_url,
                    "platform": manual_platform,
                    "social_url": manual_social_url,
                    "penulis": "",
                    "komentar": comment,
                    "like_count": 0,
                    "tanggal_komentar": "",
                })

            manual_df = pd.DataFrame(manual_rows)
            manual_df = add_comment_sentiment(manual_df)
            save_comments_to_db(manual_df)

            st.success(f"{len(manual_df)} komentar manual berhasil dianalisis.")
            st.dataframe(manual_df, use_container_width=True)

    st.divider()
    st.subheader("Ambil Komentar dari URL YouTube Manual")

    youtube_url_manual = st.text_input("URL Video YouTube atau Video ID", value="")
    youtube_theme_manual = st.text_input("Tema untuk komentar YouTube manual", value="", key="youtube_theme_manual")
    youtube_news_title_manual = st.text_input("Judul berita/topik terkait", value="", key="youtube_news_title_manual")

    if st.button("Ambil Komentar dari YouTube Manual"):
        video_id = extract_youtube_video_id(youtube_url_manual)

        if not youtube_api_key:
            st.warning("Masukkan YouTube Data API Key di sidebar terlebih dahulu.")
        elif not video_id:
            st.warning("URL atau Video ID YouTube tidak valid.")
        else:
            comments, error = fetch_youtube_comments(
                video_id=video_id,
                api_key=youtube_api_key,
                max_comments=int(max_comments_per_post)
            )

            if error:
                st.warning(error)

            if comments:
                news_row = {
                    "tema": youtube_theme_manual,
                    "sumber": "Manual YouTube",
                    "judul": youtube_news_title_manual or youtube_url_manual,
                    "link": youtube_url_manual,
                }
                comment_df = build_comment_df(comments, news_row)
                comment_df = add_comment_sentiment(comment_df)
                save_comments_to_db(comment_df)

                st.success(f"{len(comment_df)} komentar YouTube berhasil dianalisis.")
                st.dataframe(comment_df, use_container_width=True)
            else:
                st.info("Tidak ada komentar YouTube yang berhasil diambil.")


# =========================
# TAB 3: DASHBOARD BERITA
# =========================

with tab_dashboard_berita:
    st.subheader("Dashboard Hasil Sentimen Berita")

    history_df = load_history()

    if history_df.empty:
        st.info("Belum ada data berita tersimpan.")
    else:
        filter_col_1, filter_col_2 = st.columns([1, 1])

        with filter_col_1:
            selected_themes = st.multiselect(
                "Filter tema",
                sorted(history_df["tema"].dropna().unique()),
                key="berita_theme_filter"
            )

        with filter_col_2:
            selected_sentiments = st.multiselect(
                "Filter sentimen",
                ["positive", "neutral", "negative"],
                format_func=lambda x: LABEL_ID.get(x, x),
                key="berita_sentiment_filter"
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

        st.write("Distribusi Sentimen Berita")

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
            label="Download Hasil Berita CSV",
            data=csv_data,
            file_name="hasil_sentimen_berita.csv",
            mime="text/csv"
        )


# =========================
# TAB 4: DASHBOARD KOMENTAR
# =========================

with tab_dashboard_komentar:
    st.subheader("Dashboard Hasil Sentimen Komentar Sosial Media")

    comments_history_df = load_comments_history()

    if comments_history_df.empty:
        st.info("Belum ada data komentar tersimpan.")
    else:
        comment_filter_col_1, comment_filter_col_2, comment_filter_col_3 = st.columns([1, 1, 1])

        with comment_filter_col_1:
            selected_comment_themes = st.multiselect(
                "Filter tema komentar",
                sorted(comments_history_df["tema"].dropna().unique()),
                key="comment_theme_filter"
            )

        with comment_filter_col_2:
            selected_platforms = st.multiselect(
                "Filter platform",
                sorted(comments_history_df["platform"].dropna().unique()),
                key="comment_platform_filter"
            )

        with comment_filter_col_3:
            selected_comment_sentiments = st.multiselect(
                "Filter sentimen komentar",
                ["positive", "neutral", "negative"],
                format_func=lambda x: LABEL_ID.get(x, x),
                key="comment_sentiment_filter"
            )

        filtered_comments_df = comments_history_df.copy()

        if selected_comment_themes:
            filtered_comments_df = filtered_comments_df[filtered_comments_df["tema"].isin(selected_comment_themes)]

        if selected_platforms:
            filtered_comments_df = filtered_comments_df[filtered_comments_df["platform"].isin(selected_platforms)]

        if selected_comment_sentiments:
            filtered_comments_df = filtered_comments_df[
                filtered_comments_df["sentimen_komentar"].isin(selected_comment_sentiments)
            ]

        comment_metric_1, comment_metric_2, comment_metric_3, comment_metric_4 = st.columns(4)

        comment_metric_1.metric("Total Komentar", len(filtered_comments_df))
        comment_metric_2.metric("Platform", filtered_comments_df["platform"].nunique())
        comment_metric_3.metric("Berita Terkait", filtered_comments_df["judul_berita"].nunique())

        if len(filtered_comments_df) > 0:
            dominant_comment = filtered_comments_df["sentimen_komentar"].value_counts().idxmax()
            comment_metric_4.metric("Sentimen Dominan", LABEL_ID.get(dominant_comment, dominant_comment))
        else:
            comment_metric_4.metric("Sentimen Dominan", "-")

        st.write("Distribusi Sentimen Komentar")
        comment_sentiment_count = (
            filtered_comments_df["sentimen_komentar"]
            .value_counts()
            .rename(index=LABEL_ID)
        )
        st.bar_chart(comment_sentiment_count)

        st.write("Distribusi Sentimen Komentar per Platform")

        if not filtered_comments_df.empty:
            comment_pivot_platform = pd.crosstab(
                filtered_comments_df["platform"],
                filtered_comments_df["sentimen_komentar"]
            ).rename(columns=LABEL_ID)

            st.dataframe(comment_pivot_platform, use_container_width=True)

        st.write("Distribusi Sentimen Komentar per Tema")

        if not filtered_comments_df.empty:
            comment_pivot_theme = pd.crosstab(
                filtered_comments_df["tema"],
                filtered_comments_df["sentimen_komentar"]
            ).rename(columns=LABEL_ID)

            st.dataframe(comment_pivot_theme, use_container_width=True)

        st.write("Data Komentar")

        display_comments_df = filtered_comments_df.copy()
        display_comments_df["sentimen_komentar"] = display_comments_df["sentimen_komentar"].map(LABEL_ID)

        st.dataframe(
            display_comments_df[
                [
                    "tema",
                    "platform",
                    "judul_berita",
                    "sumber_berita",
                    "komentar",
                    "penulis",
                    "like_count",
                    "tanggal_komentar",
                    "sentimen_komentar",
                    "skor_komentar",
                    "social_url",
                    "link_berita",
                    "created_at"
                ]
            ],
            use_container_width=True
        )

        comments_csv_data = filtered_comments_df.to_csv(index=False).encode("utf-8")

        st.download_button(
            label="Download Hasil Komentar CSV",
            data=comments_csv_data,
            file_name="hasil_sentimen_komentar_sosial_media.csv",
            mime="text/csv"
        )
