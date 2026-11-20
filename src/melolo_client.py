#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prototype klien Linux untuk Melolo — hasil reverse engineering XAPK v5.5.4
Package: com.worldance.drama | aid aplikasi: 645713

Dua sumber data:
  1. API asli aplikasi (api.tmtreader.com) — endpoint yang tidak butuh signing/Login.
  2. Katalog publik melolo.com (sitemap + halaman drama) — fallback untuk menemukan
     drama & URL episode karena feed utama aplikasi dilindungi anti-bot native.

Hanya memakai Python standard library.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

APP_AID = "645713"
APP_VERSION = "55418"
API_BASE = "https://api.tmtreader.com"
CATALOG_BASE = "https://melolo.com"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 MeloloLinux/0.1"


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------
def request(url, method="GET", body=None, headers=None, timeout=20):
    h = {"User-Agent": USER_AGENT}
    if headers:
        h.update(headers)
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
    try:
        return json.loads(raw)
    except Exception:
        return {"_raw": raw[:2000]}


# ---------------------------------------------------------------------------
# Klien API aplikasi (api.tmtreader.com)
# ---------------------------------------------------------------------------
class MeloloAPI:
    def __init__(self, aid=APP_AID, base=API_BASE, region="ID", language="en"):
        self.aid = aid
        self.base = base.rstrip("/")
        self.region = region
        self.language = language

    def _common(self):
        # Parameter yang terlihat pada model I18nNovelCommonParam (DEX classes8.dex)
        return {
            "aid": self.aid,
            "device_platform": "android",
            "version_code": APP_VERSION,
            "app_language": self.language,
            "app_region": self.region,
            "region": self.region,
            "current_region": self.region,
            "sys_region": self.region,
            "language": self.language,
            "sys_language": self.language,
        }

    def get(self, path, **params):
        q = dict(self._common())
        q.update(params)
        url = self.base + path + "?" + urllib.parse.urlencode(q)
        return request(url)

    def post(self, path, payload, **params):
        q = dict(self._common())
        q.update(params)
        url = self.base + path + "?" + urllib.parse.urlencode(q)
        return request(url, method="POST", body=payload)

    # Endpoint yang sudah diverifikasi hidup & tidak butuh signing ----------
    def get_config(self):
        return self.get("/i18n_novel/userapi/get_config/v1/")

    def categories(self):
        return self.get("/i18n_novel/book/category/list/v1/")

    def search(self, query, offset=0, limit=10):
        return self.get("/i18n_novel/search/page/v1/",
                        query=query, offset=offset, limit=limit, search_scene=0)

    def video_detail(self, series_id, content_type=0):
        """POST /novel/player/video_detail/v1/ — butuh series_id (string)."""
        return self.post("/novel/player/video_detail/v1/", {
            "series_id": str(series_id),
            "content_type": content_type,
        })

    def multi_video_detail(self, series_ids, content_type=0):
        return self.post("/novel/player/multi_video_detail/v1/", {
            "series_id": str(series_ids),
            "content_type": content_type,
        })

    def video_model(self, video_id, content_type=0):
        return self.post("/novel/player/video_model/v1/", {
            "video_id": str(video_id),
            "content_type": content_type,
        })

    def book_detail(self, book_id):
        return self.get("/i18n_novel/book/books/detail/", book_id=str(book_id))

    def directory(self, book_id):
        return self.get("/i18n_novel/book/directory/info/v1/", book_id=str(book_id))


# ---------------------------------------------------------------------------
# Katalog publik melolo.com (fallback penemuan konten)
# ---------------------------------------------------------------------------
class Catalog:
    def __init__(self, base=CATALOG_BASE):
        self.base = base

    def _fetch(self, path):
        req = urllib.request.Request(self.base + path, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.read().decode("utf-8", "replace")

    def dramas(self, keyword=None, limit=40, hanya_dub=False):
        xml = self._fetch("/sitemap/movie.xml")
        slugs = []
        for loc in re.findall(r"<loc>([^<]+)</loc>", xml):
            m = re.search(r"/dramas/([a-z0-9-]+)/?$", loc)
            if m and m.group(1) not in slugs:
                slugs.append(m.group(1))
        if hanya_dub:
            # Slug drama versi dub Indonesia memuat kata "dub"/"dubbed".
            slugs = [s for s in slugs if "dub" in s]
        if keyword:
            k = keyword.lower()
            slugs = [s for s in slugs if k in s]
        return slugs[:limit], len(slugs)

    def _api_series(self, slug, episode_id=None, language="id"):
        """API internal situs melolo.com → data series + URL video bertanda tangan."""
        params = {
            "language": language,
            "series_slug": slug,
            "pageType": "play",
            "_refresh": "%s-%s" % (int(__import__("time").time() * 1000),
                                   __import__("random").random()),
        }
        if episode_id is not None:
            params["episode_id"] = str(episode_id)
        url = self.base + "/api/series/getSeriesBySlug?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                                   "Referer": self.base + "/"})
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.loads(r.read().decode("utf-8", "replace"))

    def series_info(self, slug, language="id"):
        d = self._api_series(slug, language=language)
        return d.get("data", [{}])[0] if d.get("data") else {}

    def episode_url(self, slug, episode_id, language="id"):
        """Ambil URL MP4 yang baru ditandatangani untuk satu episode."""
        d = self._api_series(slug, episode_id=episode_id, language=language)
        eps = (d.get("data") or [{}])[0].get("episode_list") or []
        for e in eps:
            if str(e.get("episode_id")) == str(episode_id):
                return e.get("url", "")
        return ""

    def episodes(self, slug_or_url, locale="id"):
        """Daftar episode dari API situs. locale='id' = dub Bahasa Indonesia."""
        slug = slug_or_url.strip("/").split("/")[-1] if not slug_or_url.startswith("http") else (
            re.search(r"/dramas/([a-z0-9-]+)", slug_or_url).group(1))
        info = self.series_info(slug, language=locale)
        out = []
        for e in info.get("episode_list") or []:
            n = e.get("episode_id")
            if n is not None:
                out.append({"episode": int(n), "url": e.get("url", "")})
        out.sort(key=lambda e: e["episode"])
        return slug, out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def show_json(data):
    print(json.dumps(data, indent=2, ensure_ascii=False)[:12000])


def main():
    p = argparse.ArgumentParser(
        description="Klien Linux prototipe untuk Melolo (dari reverse engineering XAPK 5.5.4)")
    p.add_argument("--region", default="ID", help="region aplikasi (default: ID)")
    p.add_argument("--lang", default="en", help="bahasa aplikasi (default: en)")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("config", help="Informasi konfigurasi backend")
    sub.add_parser("categories", help="daftar kategori drama dari API aplikasi")
    sub.add_parser("endpoints", help="tampilkan peta endpoint hasil dekompilasi")

    ps = sub.add_parser("search", help="cari di API aplikasi")
    ps.add_argument("query")

    pb = sub.add_parser("book", help="detail/daftar episode berdasarkan book_id")
    pb.add_argument("book_id")

    pv = sub.add_parser("series", help="detail series via player API (butuh series_id)")
    pv.add_argument("series_id")

    pc = sub.add_parser("catalog", help="cari drama di katalog publik melolo.com")
    pc.add_argument("keyword", nargs="?")

    pe = sub.add_parser("episodes", help="ekstrak URL episode dari halaman drama")
    pe.add_argument("slug_or_url")

    pp = sub.add_parser("play", help="putar episode dengan mpv/vlc/ffplay")
    pp.add_argument("slug_or_url")
    pp.add_argument("episode", nargs="?", type=int, default=1)

    args = p.parse_args()
    api = MeloloAPI(region=args.region, language=args.lang)
    cat = Catalog()

    if args.cmd == "config":
        show_json(api.get_config())
    elif args.cmd == "categories":
        d = api.categories()
        cats = d.get("data", {}).get("categories", [])
        print("Kategori (%d):" % len(cats))
        for c in cats:
            print("  %-6s %s" % (c.get("id"), c.get("name")))
    elif args.cmd == "endpoints":
        path = os.path.join(os.path.dirname(__file__), "api_map.json")
        try:
            data = json.load(open(path))
        except FileNotFoundError:
            print("api_map.json tidak disertakan di repo source "
                  "(hasil analisis, bukan source aplikasi).")
            return 0
        seen = set()
        for o in data.get("operations", []):
            k = (o["method"], o["path"])
            if k in seen:
                continue
            seen.add(k)
            print("%-4s %s" % (o["method"], o["path"]))
    elif args.cmd == "search":
        show_json(api.search(args.query))
    elif args.cmd == "book":
        show_json(api.book_detail(args.book_id))
        show_json(api.directory(args.book_id))
    elif args.cmd == "series":
        show_json(api.video_detail(args.series_id))
    elif args.cmd == "catalog":
        slugs, total = cat.dramas(args.keyword)
        print("Ditemukan %d drama%s:" % (total, " (menampilkan %d)" % len(slugs) if args.keyword else ""))
        for s in slugs:
            print("  https://melolo.com/dramas/" + s)
    elif args.cmd == "episodes":
        slug, eps = cat.episodes(args.slug_or_url)
        print("%s — %d episode ditemukan" % (slug, len(eps)))
        for e in eps:
            print("  %3d  %s" % (e["episode"], e["url"]))
    elif args.cmd == "play":
        slug, eps = cat.episodes(args.slug_or_url)
        ep = next((e for e in eps if e["episode"] == args.episode), None)
        if not ep:
            print("Episode %d tidak ditemukan (tersedia: %d)" %
                  (args.episode, len(eps)), file=sys.stderr)
            return 1
        players = [x for x in ("mpv", "vlc", "ffplay") if shutil.which(x)]
        if not players:
            print("Tidak ada pemutar. Install mpv/vlc/ffplay, atau buka URL ini:\n  " + ep["url"])
            return 1
        print("Memutar %s episode %d dengan %s" % (slug, args.episode, players[0]))
        player = players[0]
        if player == "mpv":
            return subprocess.call([player, "--http-header-fields=Referer: " + CATALOG_BASE + "/", ep["url"]])
        if player == "vlc":
            return subprocess.call([player, "--http-referrer=" + CATALOG_BASE + "/", ep["url"]])
        if player == "ffplay":
            hdr = "Referer: %s/\r\n" % CATALOG_BASE
            return subprocess.call([player, "-headers", hdr, ep["url"]])
        return subprocess.call([player, ep["url"]])
    else:
        p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
