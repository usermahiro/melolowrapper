# melolowrapper

Klien Linux untuk Melolo (drama pendek dub Indonesia) — hasil reverse engineering
XAPK `com.worldance.drama` v5.5.4.

## Format repository

Repo ini **hanya berisi source mentah** (base64) dan konfigurasi builder.
File `.py` yang sudah jadi **tidak disimpan di repo** — semuanya dihasilkan
saat build oleh GitHub Actions dan dirilis sebagai artefak.

```
src/
  melolo_client.py.b64      -> klien API + katalog + proxy video (source)
  melolo_gui.py.b64         -> antarmuka GUI Qt (source)
  buka.sh.b64               -> launcher
  MeloloLinux.desktop.b64   -> entry desktop
  api_map.json.b64          -> peta endpoint hasil analisis (base64)
.github/workflows/build.yml -> builder + publisher release
```

## Cara build manual

```bash
mkdir -p build
for f in src/*.b64; do
  base64 -d "$f" > "build/$(basename "$f" .b64)"
done
chmod +x build/buka.sh
python3 -m py_compile build/melolo_client.py build/melolo_gui.py
cd build && ./buka.sh
```

Butuh Python 3 + PySide6 (`pip install PySide6`).

## Cara build otomatis

- Push tag `v*`, atau jalankan workflow **Build MeloloWrapper** secara manual.
- Workflow akan mendekode semua `src/*.b64`, mengecek sintaks, membungkus
  menjadi `melolowrapper-linux.zip`, lalu meng-uploadnya ke **GitHub Release**
  dengan tag yang sama.

## Isi aplikasi hasil build

- Video tampil langsung di jendela (Qt Multimedia + FFmpeg).
- Daftar episode bisa digulir.
- Tombol **Next Eps** dan **Next Drama**.
- Hanya drama dub Bahasa Indonesia (181 drama dari katalog).
- URL video diambil segar per episode lewat API internal situs.
- Proxy lokal menambahkan header `Referer` agar CDN mengizinkan playback.

## Catatan

Ini adalah klien wrapper untuk konten publik `melolo.com`, bukan port native
dari library ARM aplikasi Android. Detail analisis ada di README hasil build.
