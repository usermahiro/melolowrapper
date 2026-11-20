# Reverse Engineering Melolo 5.5.4 → Klien Linux

Hasil analisis statis terhadap:
`/home/mahiro/Downloads/Melolo+-+Short+Dramas+&+Reels_5.5.4_APKPure.xapk`

Tanggal analisis: 2026-11-21. Semua temuan di bawah adalah **observasi statis + probe backend**
(bukan eksekusi aplikasi Android di emulator).

---

## 1. Ringkasan singkat

| Item | Nilai |
|---|---|
| Nama aplikasi | Melolo – Short Dramas & Reels |
| Package | `com.worldance.drama` |
| Versi | 5.5.4 (`version_code` 55418) |
| Min / target SDK | 23 / 36 |
| Ukuran | 169 MB (XAPK) |
| Sumber | APKPure |
| App ID backend (`aid`) | **645713** |
| Backend utama | `https://api.tmtreader.com` |
| Backend alternatif | `https://api-my.tmtreader.com` |
| Auth / device register | `https://passport.tmtreader.com` |
| Log / telemetry | `https://log.tmtreader.com` |
| Status backend | **Hidup** (merespons JSON, 2026-11-21) |

Aplikasi ini **bukan** Flutter/React Native. Ia adalah aplikasi Android native
Kotlin + Jetpack Compose yang sangat besar (18 file DEX, ~130 MB bytecode),
dengan banyak library native ARM (`armeabi-v7a`) dari ekosistem ByteDance.

Tidak ada “kode aplikasi” yang bisa dikompilasi ulang untuk Linux. Klien Linux
harus berupa **reimplementasi protokol jaringan** yang bicara ke backend yang sama.

---

## 2. Struktur XAPK

```
manifest.json                 (xapk_version 2, split configs)
com.worldance.drama.apk       (146.946.770 byte) — APK utama
config.armeabi_v7a.apk        ( 21.684.851 byte) — library native ARM 32-bit
config.mdpi.apk               (    434.315 byte) — resource kepadatan layar
icon.png
```

Isi APK utama:
- `classes.dex` … `classes18.dex` — 18 DEX, total ~130 MB
- `assets/` — Lottie JSON, font (Literata, Merriweather, NotoSerif, dll.),
  file locale (60+ bahasa), konfigurasi iklan (Pangle/AppLovin/Moloco/Vungle)
- `AndroidManifest.xml` — binary XML
- Tidak ada `.so` di APK utama; semua `.so` ada di split `armeabi-v7a`.

Contoh library native yang relevan (dari `config.armeabi_v7a.apk`):
`libmetasec_ml.so`, `libbdhm_native.so`, `libpglarmor.so`, `libnpth_*.so`
(anti-bot / risk control), `libByteVC1_dec.so`, `libbyteVC2dec.so`,
`libaudioeffect.so`, `liblynx.so`, `libmmkv.so`, `libapplog_rust.so`.

---

## 3. Metode & tooling

Karena tidak ada REA MCP / JADX / Java di lingkungan awal, saya menyiapkan:

1. **JADX CLI 1.5.7** + **Temurin JRE 21** (diunduh ke `/tmp/re_tools`).
2. Dekompilasi per-DEX (heap 900 MB) karena dekompilasi seluruh APK gagal
   (OOM pada 3,6 GB RAM): total **70.059 file `.java`** di `/tmp/melolo_re/out_dex*/sources`.
3. `strings` pada DEX untuk memetakan string API ke file DEX.
4. `pyaxmlparser` untuk membaca `AndroidManifest.xml`.
5. Probe langsung ke backend dengan `curl` untuk memverifikasi endpoint & parameter.

Catatan: JADX melaporkan banyak error dekompilasi (Kotlin metadata rusak /
referensi lintas-DEX hilang), tetapi cukup untuk membaca annotation `@RpcOperation`,
`@SerializedName`, dan struktur model request/response.

---

## 4. Arsitektur jaringan (temuan utama)

### 4.1 RPC framework custom ByteDance

Aplikasi memakai `com.bytedance.rpc` dengan pola:

```java
@RpcOperation("$GET /i18n_novel/bookmall/tab/v1/")
@RpcParams(true)
@RpcSerializer(SerializeType.JSON)   // atau SerializeType.PB
Observable<GetBookMallHomePageResponse> getBookMallHomePageRxJava(GetBookMallHomePageRequest req);
```

Bukti (decompiled):
- `out_dex3/sources/com/worldance/novel/pbrpc/I18NNovelPbapi.java` (serializer **PB**)
- `out_dex7/sources/com/worldance/novel/rpc/rpc/BookMallApiService.java` (serializer **JSON**)
- `out_dex12/sources/seriessdk/com/dragon/read/saas/rpc/rpc/PlayerApiService.java`

Total **143 deklarasi operasi RPC** ditemukan (setelah deduplikasi ~120 endpoint unik).
Peta lengkap ada di `api_map.json` (method, path, serializer, tipe request, file sumber).

### 4.2 Serializer

| Serializer | Jumlah deklarasi | Catatan |
|---|---|---|
| JSON | 134 | Mayoritas endpoint; field request memakai `@SerializedName` → nama query/body |
| PB (protobuf) | 3 | Feed utama `bookmall/tab`, `cell/change`, `plan`; skema bisa direkonstruksi dari field number di model Wire |
| FORM | 2 | endpoint generik |

Contoh model protobuf: `out_dex2/sources/com/worldance/novel/pbrpc/GetBookMallHomePageRequest.java`
berisi field bernomor 1–58, 251–254 (`tab_type`, `offset`, `limit`,
`novel_common_param`, `common_param`, dll.).

Contoh model JSON: `out_dex9/sources/com/worldance/novel/rpc/model/GetBookMallHomePageRequest.java`
— setiap field punya `@SerializedName("...")` dan `@RpcField(FieldType.QUERY)`.

### 4.3 Header & parameter umum

Dari `I18nNovelCommonParam` (`out_dex8/.../rpc/model/I18nNovelCommonParam.java`):

- **Header**: `Age-Range`, `Sign-Env`, `Sign-Res`, `Client-Install-Id`,
  `X-Forwarded-For`, `X-Xs-From-Web`, `User-Agent`, `X-Xs-Web-Imgfmt`
- **Query**: `app_language`, `app_region`, `region`, `current_region`,
  `sys_region`, `sys_language`, `language`, `carrier_region`, `mcc_mnc`,
  `device_dpi`, `time_zone`, `image_control`, dll.
- **Wajib**: `aid=645713` (tanpa ini semua endpoint balas `{"code":123,"message":"invalid aid"}`).

### 4.4 Endpoint player (paling mudah dipakai)

```java
POST /novel/player/video_detail/v1/
POST /novel/player/video_model/v1/
POST /novel/player/multi_video_detail/v1/
POST /novel/player/multi_video_model/v1/
```
Request (`GetVideoDetailRequest`, `out_dex14/.../GetVideoDetailRequest.java`):
```json
{ "series_id": "<id>", "content_type": 0, "biz_param": {}, "NovelCommonParam": {} }
```

---

## 5. Hasil probe backend (2026-11-21)

Semua dengan `aid=645713`:

| Endpoint | Hasil |
|---|---|
| `GET /i18n_novel/userapi/get_config/v1/` | `{"code":0,"message":"SUCCESS"}` ✅ |
| `GET /i18n_novel/book/category/list/v1/` | `{"code":0,...}` + 40+ kategori (Romance, Billionaire, Paranormal, …) ✅ |
| `GET /i18n_novel/search/page/v1/?query=...` | `code:0`, tapi `search_data:[]` (butuh user/device context) ⚠️ |
| `GET /i18n_novel/bookmall/tab/v1/` | `code:1050007 BOOKMALL_RISK_CONTROL_ERROR` ❌ |
| `GET /novel/player/video_detail/v1/` (GET) | `invalid param` ❌ (harus POST) |
| `POST /novel/player/video_detail/v1/` `{"series_id":"1"}` | `101001 该剧集已下架` (param benar, id 1 tidak valid) ✅ |
| `POST /novel/player/multi_video_detail/v1/` `{"series_id":"1"}` | `code:0` + objek video_data ✅ |
| `GET /i18n_novel/userapi/get_frontier_config/v1/` | `wss://frontier.tmtreader.com/ws/v2` ✅ |
| `GET /i18n_novel/book/directory/info/v1/?book_id=1` | `1000001 BOOKAPI_BOOK_REMOVE_ERROR` (param `book_id` benar) |

Kesimpulan: **API asli bisa diajak bicara**, tetapi feed utama (`bookmall/tab`)
diblokir oleh risk control.

---

## 6. Blocker utama (jujur)

1. **Anti-bot / signing native.** Header `Sign-Env` dan `Sign-Res` tidak pernah
   diisi di kode Java yang berhasil didekompilasi (grep `checkSignEnv =`,
   `checkSignResult =` tidak menemukan assignment). Nilainya hampir pasti
   dihasilkan oleh library native (`libmetasec_ml.so`, `libbdhm_native.so`,
   `libpglarmor.so`, `libnpth_*.so`) yang hanya tersedia untuk **armeabi-v7a**.
   Tanpa itu, `bookmall/tab` (feed beranda) balas `BOOKMALL_RISK_CONTROL_ERROR`.

2. **Auth / device registration.** Endpoint `get_homepage`, pencarian, dll.
   membutuhkan `user_id`/token. Registrasi device lewat
   `passport.tmtreader.com/service/2/device_register/` juga memakai
   `TeaConfig` + enkripsi aplikasi (`MeloloAppLogInitializer`,
   `out_dex0/sources/com/worldance/novel/launch/melolo/tasks/MeloloAppLogInitializer.java`).

3. **Arsitektur ARM.** Semua `.so` hanya 32-bit ARM; tidak bisa dimuat langsung
   di x86-64 Linux. Replikasi signing butuh reverse engineering library native
   tersebut (Ghidra/IDA) atau menjalankannya di emulator/ARM host (mis. QEMU).

4. **Berbayar/iklan.** VIP, billing, dan iklan terikat Play Billing / SDK pihak
   ketiga; tidak relevan untuk klien Linux dasar.

---

## 7. Jalur alternatif yang ditemukan (katalog publik)

`https://melolo.com` (berbeda dari `www.melolo.org` yang dipakai aplikasi) adalah
situs katalog publik dengan `robots.txt` mengizinkan crawl dan sitemap:

- `https://melolo.com/sitemap.xml` → `sitemap/movie.xml` (4.913 drama).
- Filter `dub`/`dubbed` pada slug → **181 drama versi suara dubbing**.
- API internal situs (ketemu dari chunk JS `3y10qxelhr0j0.js`):

  ```
  GET /api/series/getSeriesBySlug?language=id&series_slug=<slug>
      &pageType=play&episode_id=<N>&_refresh=<acak>
  ```

  Mengembalikan `data[0].episode_list` dengan **URL MP4 bertanda tangan segar**
  untuk episode yang diminta, plus metadata `series_id`, `langs` (mis. `en,id,pt`),
  dan judul Indonesia seperti `[Versi suara dubbing] Cinta terputus sang putri`.

Dua temuan penting:
1. `language=id` memilih **audio dub Bahasa Indonesia** (URL videonya berbeda
   dari `language=en`) — bukan sekadar subtitle.
2. Tanda tangan URL hanya berlaku untuk episode yang diminta, jadi URL harus
   diambil ulang lewat API setiap kali berpindah episode (dulu menyebabkan
   `403/502` bila memakai URL dari HTML statis).

Aplikasi memutar video lewat proxy lokal kecil yang menambahkan header
`Referer: https://melolo.com/` — tanpa header itu CDN menolak request (`403`).

---

## 8. Aplikasi GUI Linux

**Cara paling mudah — buka GUI:**
```bash
cd /home/mahiro/melolo-linux
./buka.sh
```
Atau klik 2x `MeloloLinux.desktop` (bisa dipindah ke `~/.local/share/applications/`).

Tampilan akhir (sesuai permintaan):
- **Daftar drama tidak ditampilkan** — langsung masuk ke drama dub Indonesia pertama.
- Video **muncul langsung di dalam jendela** (bukan jendela mpv terpisah).
- Daftar episode di kanan bisa **digulir**; klik episode untuk berpindah.
- Tombol bawah: **Next Eps** (episode berikutnya) dan **Next Drama** (drama dub berikutnya).
- Saat episode selesai, muncul tombol **Buka Episode Berikutnya** di atas video.
- Seluruh teks antarmuka berbahasa Indonesia, judul drama juga diambil dalam bahasa Indonesia.

Sudah ditest: 181 drama dub termuat, otomatis memutar Episode 1, Next Eps → Episode 2
lanjut normal, Next Drama → drama dub lain langsung terputar.

Catatan: di lingkungan ini Qt perlu `QT_QPA_PLATFORM=xcb` (sudah diatur di `buka.sh`).

**Mode CLI** (tetap ada, untuk scripting/debugging):
```bash
./buka.sh cli categories          # kategori dari API asli
./buka.sh cli config              # cek koneksi backend
./buka.sh cli catalog love        # cari drama di katalog publik
./buka.sh cli episodes <slug>     # daftar URL episode
./buka.sh cli play <slug> 1       # putar via mpv/vlc/ffplay
./buka.sh cli series <series_id>  # detail via player API asli
```

Contoh keluaran `episodes ring-of-power` (dari halaman publik):
```
ring-of-power — 34 episode ditemukan
    1  https://v.melolo.com/.../v.f101303.mp4?sign=...
    2  https://v.melolo.com/.../v.f101303.mp4
    ...
```

Catatan: URL video CDN menolak request tanpa header `Referer: https://melolo.com/`
(verifikasi: `HTTP 403` tanpa header, `HTTP 206 video/mp4` dengan header).
Perintah `play` sudah mengirim header tersebut lewat mpv/vlc/ffplay.

---

## 9. Batasan & langkah berikutnya

- **Sudah terjawab**: identitas artefak, tech stack, host backend, app ID, peta
  endpoint + nama parameter, format request/response, status live endpoint.
- **Parsial**: katalog & URL episode (lewat situs publik); API player (butuh
  series_id dari sumber eksternal).
- **Belum terselesaikan**: feed beranda & pencarian bermakna, login/akun, riwayat,
  VIP — semuanya terhalang signing native + auth.
- **Lanjutan yang disarankan**:
  1. Reverse `libmetasec_ml.so` / `libbdhm_native.so` dengan Ghidra untuk
     menghasilkan `Sign-Env`/`Sign-Res` (butuh host ARM atauQL emulation).
  2. Rekam traffic asli dari perangkat Android/emulator untuk menangkap header
     dan protobuf payload feed, lalu generate `.proto` dari model Wire.
  3. Rekonstruksi alur `device_register` + token agar endpoint user bisa dipakai.
  4. Bangun UI desktop (GTK/Qt/Electron) di atas `MeloloAPI` setelah (1)–(3).

---

## 10. Evidence ledger (ringkas)

| Klaim | Bukti |
|---|---|
| Aplikasi native Kotlin/Compose | `META-INF/androidx.compose.*.version`, 18 `classes*.dex` |
| Package & versi | `manifest.json`; `AndroidManifest.xml.decoded` (`SS_VERSION_CODE=55418`) |
| App ID 645713 | string `worldance645713://` di DEX; probe `?aid=645713` → `code:0` |
| Backend hosts | `strings dex/*.dex` → `api.tmtreader.com`, `passport.tmtreader.com`, `log.tmtreader.com` |
| 143 operasi RPC | `api_map.json`, diekstrak dari annotation `@RpcOperation` di 70k file decompiled |
| Serializer PB/JSON | `I18NNovelPbapi.java` vs `BookMallApiService.java` |
| Endpoint player POST JSON | `PlayerApiService.java` + probe POST berhasil |
| Risk control feed | probe `GET /i18n_novel/bookmall/tab/v1/` → `1050007` |
| Sign header dari native | `I18nNovelCommonParam.java`; tidak ada assignment Java; `.so` anti-bot di split ARM |
| Katalog publik | `melolo.com/sitemap.xml`, `robots.txt`, halaman drama berisi URL MP4 |

Artefak kerja lengkap (DEX, source hasil dekompilasi, log, dan `api_map.json`)
adalah hasil analisis dan **tidak disertakan** di repo source ini — repositori ini
hanya berisi kode aplikasi klien. Daftar endpoint sudah dirangkum di README ini.
