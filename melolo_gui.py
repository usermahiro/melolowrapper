#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Melolo Linux — antarmuka penuh bahasa Indonesia.
Hanya drama dub Indonesia. Video tampil langsung di jendela, daftar episode
bisa digulir. Tombol: "Next Eps" dan "Next Drama".

Video diputar lewat proxy lokal karena CDN video memerlukan header Referer.
"""
import re
import sys
import threading
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PySide6.QtCore import QObject, QThread, QTimer, QUrl, Signal, Slot, Qt
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QLabel, QScrollArea, QGridLayout,
    QStackedWidget, QStatusBar, QSplitter,
)

from melolo_client import Catalog, CATALOG_BASE

cat = Catalog()

STYLE = """
QMainWindow, QWidget { background:#0d0d14; color:#f2f2f5; font-family:'Segoe UI',sans-serif; }
QLineEdit { background:#1a1a26; border:1px solid #333; border-radius:8px; padding:10px; color:#fff; font-size:13px; }
QPushButton { background:#ff4d7d; color:white; border:0; border-radius:8px; padding:11px 18px; font-weight:bold; font-size:13px; }
QPushButton:hover { background:#ff6f96; }
QPushButton#episode { background:#1e1e2c; border:1px solid #333; padding:9px 2px; font-size:11px; }
QPushButton#episode:hover { background:#ff4d7d; }
QPushButton#aktif { background:#ff4d7d; padding:9px 2px; font-size:11px; }
QScrollArea { border:0; background:#0d0d14; }
QLabel#judul { font-size:21px; font-weight:bold; }
QLabel#kecil { color:#9a9ab0; font-size:12px; }
QPushButton#lanjut { font-size:16px; padding:14px 26px; }
QStatusBar { background:#000; color:#7fe08a; }
"""


# ---------------------------------------------------------------------------
# Proxy video lokal (menambahkan header Referer untuk CDN)
# ---------------------------------------------------------------------------
class ProxyHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        try:
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            url = urllib.parse.unquote(q.get("u", [""])[0])
            headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)",
                       "Referer": CATALOG_BASE + "/"}
            rentang = self.headers.get("Range")
            if rentang:
                headers["Range"] = rentang
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
                self.send_response(r.status)
                for h in ("Content-Type", "Content-Length", "Accept-Ranges", "Content-Range"):
                    if h in r.headers:
                        self.send_header(h, r.headers[h])
                self.end_headers()
                while True:
                    bagian = r.read(65536)
                    if not bagian:
                        break
                    self.wfile.write(bagian)
        except Exception:
            try:
                self.send_error(502)
            except Exception:
                pass


def mulai_proxy():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), ProxyHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv.server_address[1]


PROXY_PORT = mulai_proxy()


# ---------------------------------------------------------------------------
# Pengambil data di latar belakang
# ---------------------------------------------------------------------------
class Pengambil(QObject):
    hasil = Signal(str, str, object)
    gagal = Signal(str)

    @Slot(str, str, str)
    def ambil(self, kunci, jenis, nilai):
        try:
            if jenis == "katalog":
                data = cat.dramas(nilai, limit=200, hanya_dub=True)
            elif jenis == "episode":
                _, data = cat.episodes(nilai)
            elif jenis == "url":
                slug, ep = nilai.split("|", 1)
                data = cat.episode_url(slug, int(ep))
            elif jenis == "info":
                info = cat.series_info(nilai)
                data = {"nama": info.get("name", ""), "bahasa": info.get("langs", ""),
                        "jumlah": info.get("episode_num", 0)}
            else:
                data = None
            self.hasil.emit(kunci, jenis, data)
        except Exception as e:
            self.gagal.emit(str(e))


# ---------------------------------------------------------------------------
# Jendela utama
# ---------------------------------------------------------------------------
class JendelaUtama(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Melolo Linux — Drama Dub Indonesia")
        self.resize(1100, 780)
        self.setStyleSheet(STYLE)
        self.daftar = []
        self.indeks_drama = -1
        self.episode = []
        self.indeks_episode = -1
        self.slug = ""

        utas = QThread()
        self.pengambil = Pengambil()
        self.pengambil.moveToThread(utas)
        self.pengambil.hasil.connect(self.saat_hasil)
        self.pengambil.gagal.connect(lambda e: self.status.showMessage("Galat: " + e))
        utas.start()
        self.utas = utas

        pusat = QWidget()
        self.setCentralWidget(pusat)
        pokok = QVBoxLayout(pusat)
        pokok.setContentsMargins(0, 0, 0, 0)

        atas = QHBoxLayout()
        atas.setContentsMargins(14, 10, 14, 8)
        label_app = QLabel("🎬 Melolo Linux")
        label_app.setObjectName("judul")
        self.cari = QLineEdit()
        self.cari.setPlaceholderText("Cari drama dub Indonesia (kosongkan untuk semua)...")
        self.cari.returnPressed.connect(self.cari_drama)
        tombol_cari = QPushButton("Cari")
        tombol_cari.clicked.connect(self.cari_drama)
        atas.addWidget(label_app)
        atas.addSpacing(24)
        atas.addWidget(self.cari)
        atas.addWidget(tombol_cari)
        pokok.addLayout(atas)

        pembagi = QSplitter(Qt.Horizontal)
        pembagi.addWidget(self.buat_pemutar())
        pembagi.addWidget(self.buat_episode())
        pembagi.setSizes([780, 260])
        pokok.addWidget(pembagi)

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Memuat drama dub Indonesia...")
        QTimer.singleShot(250, lambda: self.pengambil.ambil("awal", "katalog", ""))

    def buat_pemutar(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(14, 0, 12, 8)

        self.judul = QLabel("Memuat drama...")
        self.judul.setObjectName("judul")
        self.judul.setWordWrap(True)
        v.addWidget(self.judul)
        self.keterangan = QLabel("Video dub Indonesia akan tampil di sini.")
        self.keterangan.setObjectName("kecil")
        v.addWidget(self.keterangan)

        self.tumpukan = QStackedWidget()
        self.video = QVideoWidget()
        self.video.setMinimumSize(300, 480)
        self.tumpukan.addWidget(self.video)

        selesai = QWidget()
        sv = QVBoxLayout(selesai)
        sv.setAlignment(Qt.AlignCenter)
        t = QLabel("Episode selesai")
        t.setAlignment(Qt.AlignCenter)
        t.setStyleSheet("font-size:22px;font-weight:bold;color:#fff;")
        self.tombol_lanjut = QPushButton("Buka Episode Berikutnya")
        self.tombol_lanjut.setObjectName("lanjut")
        self.tombol_lanjut.clicked.connect(self.next_eps)
        sv.addWidget(t)
        sv.addSpacing(14)
        sv.addWidget(self.tombol_lanjut)
        self.tumpukan.addWidget(selesai)
        self.tumpukan.setCurrentIndex(0)
        v.addWidget(self.tumpukan, 1)

        kendali = QHBoxLayout()
        self.tombol_next_eps = QPushButton("Next Eps")
        self.tombol_next_eps.clicked.connect(self.next_eps)
        self.tombol_next_drama = QPushButton("Next Drama")
        self.tombol_next_drama.clicked.connect(self.next_drama)
        kendali.addWidget(self.tombol_next_eps)
        kendali.addWidget(self.tombol_next_drama)
        kendali.addStretch()
        v.addLayout(kendali)

        self.pemutar = QMediaPlayer()
        self.suara = QAudioOutput()
        self.pemutar.setAudioOutput(self.suara)
        self.pemutar.setVideoOutput(self.video)
        self.pemutar.mediaStatusChanged.connect(self.saat_status)
        return w

    def buat_episode(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 8, 8)
        l = QLabel("Daftar Episode")
        l.setObjectName("kecil")
        v.addWidget(l)
        gulir = QScrollArea()
        gulir.setWidgetResizable(True)
        wadah = QWidget()
        self.grid = QGridLayout(wadah)
        self.grid.setAlignment(Qt.AlignTop)
        self.grid.setContentsMargins(2, 2, 2, 2)
        gulir.setWidget(wadah)
        v.addWidget(gulir)
        return w

    # ---- aksi ----
    def cari_drama(self):
        self.pengambil.ambil("cari", "katalog", self.cari.text().strip())

    def saat_hasil(self, kunci, jenis, data):
        if jenis == "katalog":
            self.daftar, jumlah = data
            self.indeks_drama = 0 if self.daftar else -1
            self.status.showMessage("%d drama dub Indonesia ditemukan" % jumlah)
            if self.daftar:
                self.buka_drama(0)
            else:
                self.judul.setText("Tidak ada drama ditemukan")
        elif jenis == "info":
            if data.get("nama"):
                self.nama_series = data["nama"]
            if self.indeks_episode >= 0 and self.indeks_episode < len(self.episode):
                self.judul.setText("%s — Episode %d" % (
                    self.nama_series, self.episode[self.indeks_episode]["episode"]))
            elif data.get("nama"):
                self.judul.setText(data["nama"])
        elif jenis == "url":
            indeks = int(kunci.split(":", 1)[1])
            if not data:
                self.status.showMessage("Gagal mendapatkan URL video.")
                return
            alamat = "http://127.0.0.1:%d/?u=%s" % (PROXY_PORT, urllib.parse.quote(data, safe=""))
            self.tumpukan.setCurrentIndex(0)
            self.pemutar.setSource(QUrl(alamat))
            self.pemutar.play()
            self.status.showMessage("Memutar Episode %d (dub Indonesia)" % self.episode[indeks]["episode"])
        elif jenis == "episode":
            for i in reversed(range(self.grid.count())):
                b = self.grid.itemAt(i).widget()
                if b:
                    b.deleteLater()
            self.episode = data
            for n, e in enumerate(data):
                b = QPushButton("Ep %d" % e["episode"])
                b.setObjectName("episode")
                b.clicked.connect(lambda _, i=n: self.putar(i))
                self.grid.addWidget(b, n // 4, n % 4)
            self.keterangan.setText("%d episode tersedia — gulir untuk melihat lainnya." % len(data))
            if self.episode:
                self.putar(0)

    def buka_drama(self, indeks):
        if not (0 <= indeks < len(self.daftar)):
            return
        self.indeks_drama = indeks
        self.slug = self.daftar[indeks]
        self.nama_series = ""
        self.judul.setText("Memuat: " + self.slug.replace("-", " ").title())
        self.status.showMessage("Memuat: " + self.slug)
        self.pemutar.stop()
        self.tumpukan.setCurrentIndex(0)
        self.pengambil.ambil("info", "info", self.slug)
        self.pengambil.ambil("ep", "episode", self.slug)

    def putar(self, indeks):
        if not (0 <= indeks < len(self.episode)):
            return
        self.indeks_episode = indeks
        e = self.episode[indeks]
        self.pemutar.stop()
        self.tumpukan.setCurrentIndex(0)
        nama = getattr(self, "nama_series", "") or self.slug.replace("-", " ").title()
        self.judul.setText("%s — Episode %d" % (nama, e["episode"]))
        self.status.showMessage("Menyiapkan Episode %d..." % e["episode"])
        self.pengambil.ambil("url:%d" % indeks, "url", "%s|%d" % (self.slug, e["episode"]))
        for i in range(self.grid.count()):
            b = self.grid.itemAt(i).widget()
            if b:
                b.setObjectName("aktif" if i == indeks else "episode")
                b.setStyleSheet("background:#ff4d7d;" if i == indeks else "")

    def next_eps(self):
        if self.indeks_episode + 1 < len(self.episode):
            self.putar(self.indeks_episode + 1)
        else:
            self.status.showMessage("Sudah episode terakhir. Klik Next Drama.")

    def next_drama(self):
        if self.indeks_drama + 1 < len(self.daftar):
            self.buka_drama(self.indeks_drama + 1)
        else:
            self.status.showMessage("Sudah drama terakhir.")

    def saat_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.tumpukan.setCurrentIndex(1)
            self.status.showMessage("Episode selesai — klik 'Buka Episode Berikutnya'.")

    def closeEvent(self, e):
        self.pemutar.stop()
        self.utas.quit()
        self.utas.wait()
        e.accept()


def main():
    app = QApplication(sys.argv)
    j = JendelaUtama()
    j.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
