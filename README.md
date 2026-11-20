# melolowrapper

Klien Linux untuk Melolo (drama pendek dub Indonesia) — hasil reverse engineering
XAPK `com.worldance.drama` v5.5.4.

## Format repository

Repo ini berisi **source mentah** (Python) dan konfigurasi builder. File hasil
build tidak disimpan di repo; GitHub Actions mengemasnya lalu meng-upload ke
**GitHub Release**.

```
src/
  melolo_client.py      klien API, katalog drama dub, proxy video
  melolo_gui.py         antarmuka GUI Qt
  api_map.json          peta endpoint hasil analisis
  buka.sh               launcher
  MeloloLinux.desktop   entry desktop
.github/workflows/build.yml   builder + publisher release
```

## Build manual

```bash
cp src/* build/
chmod +x build/buka.sh
cd build && ./buka.sh
```

Butuh Python 3 + PySide6 (`pip install PySide6`).

## Build otomatis

Push tag `v*` atau jalankan workflow **Build MeloloWrapper** secara manual.
Workflow mengecek sintaks, membungkus `src/` menjadi `melolowrapper-linux.zip`,
lalu meng-uploadnya ke Release dengan tag yang sama.

## Isi aplikasi

- Video tampil langsung di jendela (Qt Multimedia + FFmpeg).
- Daftar episode bisa digulir.
- Tombol **Next Eps** dan **Next Drama**.
- Hanya drama dub Bahasa Indonesia (181 drama).
- URL video diambil segar per episode lewat API internal situs.
- Proxy lokal menambahkan header `Referer` agar CDN mengizinkan playback.

## Catatan

Ini wrapper klien untuk konten publik `melolo.com`, bukan port native dari
library ARM aplikasi Android.
