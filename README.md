# Sistem Analisis Sentimen Berita dan Komentar Sosial Media

Aplikasi ini dibuat dengan Python dan Streamlit untuk:

1. Menginput tema secara manual atau dari file CSV/Excel.
2. Mengambil berita dari Google News RSS dan RSS tambahan.
3. Menganalisis sentimen berita menjadi positif, netral, atau negatif.
4. Menyimpan hasil berita ke database SQLite.
5. Mengambil komentar sosial media yang berkaitan dengan berita.
6. Menganalisis sentimen komentar sosial media.
7. Menampilkan dashboard berita dan dashboard komentar.
8. Mengunduh hasil analisis dalam format CSV.

## Fitur Utama

### 1. Analisis Sentimen Berita

- Input tema manual, satu tema per baris.
- Upload file CSV/Excel yang memiliki kolom tema.
- Ambil berita dari Google News RSS.
- Ambil berita dari lebih dari 10 RSS bawaan.
- Tambah atau ubah RSS dari sidebar.
- Analisis sentimen judul dan ringkasan berita.
- Simpan hasil ke SQLite.

### 2. Analisis Komentar Sosial Media

Modul komentar sosial media terdiri dari tiga cara:

1. **Otomatis berdasarkan berita tersimpan**
   - Pilih berita yang sudah tersimpan.
   - Sistem membuat query dari judul berita dan tema.
   - Sistem mencari video YouTube terkait berita.
   - Sistem mengambil komentar YouTube.
   - Sistem mencari post Reddit terkait berita.
   - Sistem mengambil komentar Reddit.
   - Komentar dianalisis sentimennya dan disimpan.

2. **Input komentar manual**
   - Cocok untuk Instagram, TikTok, X/Twitter, Facebook, atau platform lain.
   - Salin komentar secara manual, satu komentar per baris.
   - Sistem menganalisis sentimen komentar tersebut.

3. **Input URL YouTube manual**
   - Masukkan URL video YouTube atau video ID.
   - Sistem mengambil komentar dari video tersebut.
   - Komentar dianalisis dan disimpan.

## Catatan Penting Sosial Media

- YouTube membutuhkan **YouTube Data API Key**.
- Reddit menggunakan endpoint JSON publik dan bisa saja dibatasi oleh Reddit atau hosting.
- Instagram, TikTok, Facebook, dan X/Twitter tidak di-scrape otomatis karena umumnya membutuhkan akses resmi, login, API khusus, atau memiliki pembatasan platform.
- Untuk platform tersebut, gunakan fitur **Input Komentar Manual**.

## Sumber RSS Bawaan

Daftar awal RSS yang tersedia di sidebar:

1. ANTARA Terkini
2. ANTARA Top News
3. ANTARA Politik
4. ANTARA Hukum
5. ANTARA Ekonomi
6. ANTARA Dunia
7. ANTARA Olahraga
8. ANTARA Teknologi
9. CNN Indonesia Nasional
10. CNN Indonesia Ekonomi
11. CNN Indonesia Teknologi
12. Tempo Nasional
13. Tempo Bisnis
14. CNBC Indonesia News
15. CNBC Indonesia Market
16. Liputan6 News
17. Suara News
18. Republika Nasional

Daftar ini tetap bisa diedit dari sidebar aplikasi dengan format:

```text
Nama Sumber|URL RSS
```

## Struktur Folder

```text
sentimen_berita_streamlit/
├── app.py
├── requirements.txt
├── runtime.txt
├── README.md
└── data/
```

## Cara Instalasi Lokal

### Windows

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

### Mac/Linux

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Cara Deploy ke Streamlit Cloud

1. Upload semua file ke repository GitHub.
2. Pastikan file berikut ada di root folder project:
   - `app.py`
   - `requirements.txt`
   - `runtime.txt`
3. Redeploy aplikasi di Streamlit Cloud.
4. Jika sebelumnya sudah pernah deploy, klik **Manage app** lalu pilih **Reboot app** atau **Clear cache**.

## Cara Menggunakan Modul Komentar Sosial Media

### A. YouTube Otomatis dari Berita

1. Jalankan analisis berita terlebih dahulu.
2. Buka tab **Analisis Komentar Sosial Media**.
3. Masukkan **YouTube Data API Key** di sidebar.
4. Pilih berita yang ingin dicari komentarnya.
5. Klik **Ambil & Analisis Komentar Sosial Media**.
6. Lihat hasil di tab **Dashboard Komentar**.

### B. Reddit Otomatis dari Berita

1. Jalankan analisis berita terlebih dahulu.
2. Buka tab **Analisis Komentar Sosial Media**.
3. Aktifkan checkbox **Reddit publik**.
4. Isi subreddit jika ingin membatasi pencarian, misalnya `indonesia`.
5. Klik **Ambil & Analisis Komentar Sosial Media**.

### C. Komentar Manual

1. Buka tab **Analisis Komentar Sosial Media**.
2. Pilih platform.
3. Masukkan URL postingan jika ada.
4. Salin komentar, satu komentar per baris.
5. Klik **Analisis Komentar Manual**.

## Format Input Tema Manual

```text
BPJS Kesehatan
IKN
Pemilu
Harga Beras
Pendidikan
```

## Format File Excel/CSV

Minimal memiliki satu kolom yang berisi tema, contoh:

| tema |
|---|
| BPJS Kesehatan |
| IKN |
| Pemilu |

## Output Data

Aplikasi menghasilkan dua jenis data:

1. **Data Berita**
   - tema
   - sumber
   - judul
   - ringkasan
   - link
   - tanggal publikasi
   - sentimen berita
   - skor sentimen

2. **Data Komentar Sosial Media**
   - tema
   - platform
   - judul berita terkait
   - komentar
   - penulis
   - jumlah like/upvote jika tersedia
   - tanggal komentar
   - sentimen komentar
   - skor sentimen komentar
   - URL sosial media
   - link berita

## Catatan

Aplikasi ini menganalisis judul/ringkasan berita dari RSS dan teks komentar sosial media. Untuk analisis berita yang lebih mendalam, sistem dapat dikembangkan dengan scraping isi artikel lengkap.
