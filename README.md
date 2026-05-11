# Sistem Analisis Sentimen Berita Berbasis Tema

Aplikasi ini dibuat dengan Python dan Streamlit untuk:

1. Menginput tema secara manual atau dari file CSV/Excel.
2. Mengambil berita dari Google News RSS dan RSS tambahan.
3. Menganalisis sentimen berita menjadi positif, netral, atau negatif.
4. Menyimpan hasil ke database SQLite.
5. Menampilkan dashboard hasil analisis dan menyediakan fitur download CSV.

## Struktur Folder

```text
sentimen_berita_streamlit/
├── app.py
├── requirements.txt
├── README.md
└── data/
```

## Cara Instalasi

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

## Format Input Tema Manual

Masukkan satu tema per baris, contoh:

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

## Catatan

Aplikasi ini menganalisis judul dan ringkasan berita dari RSS. Untuk hasil yang lebih mendalam, sistem dapat dikembangkan dengan scraping isi artikel lengkap.
