# Sistem Analisis Sentimen Berita Berbasis Tema

Aplikasi ini dibuat dengan Python dan Streamlit untuk:

1. Menginput tema secara manual atau dari file CSV/Excel.
2. Mengambil berita dari Google News RSS dan RSS tambahan.
3. Menganalisis sentimen berita menjadi positif, netral, atau negatif.
4. Menyimpan hasil ke database SQLite.
5. Menampilkan dashboard hasil analisis dan menyediakan fitur download CSV.

## Perbaikan Versi Ini

Versi ini sudah diperbaiki agar tidak crash ketika salah satu sumber RSS menutup koneksi atau tidak memberi respons.

Perubahan utama:

- Menambahkan `requests` dengan `User-Agent`, timeout, redirect, dan retry.
- Jika satu sumber RSS gagal, aplikasi hanya menampilkan peringatan dan tetap lanjut ke sumber lain.
- Menambahkan `runtime.txt` agar Streamlit Cloud menggunakan Python 3.11 yang lebih stabil untuk `torch` dan `transformers`.

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
