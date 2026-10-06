#!/usr/bin/env python3
"""
build.py — assembles the final, GitHub-safe, self-contained SVG assets.

  1. Fetches once & caches: Space Grotesk 700 + JetBrains Mono 400 (woff2, latin)
     with their SIL OFL licenses, and Simple Icons (CC0) path data for every mark.
  2. Base64-embeds your two photos (verbatim pixels, alpha preserved) + fonts +
     icons into src/*.svg templates -> writes final assets/*.svg.
  3. Verifies: unique ids, zero external refs, no script/foreignObject, no tokens.
  4. Writes upload-me.zip (README.md + assets/ + font licenses).

Usage:
  pip install pillow            # optional — auto-downsizes photos
  python3 build.py              # first run needs network
  python3 build.py --no-fetch   # offline, using caches only
"""
import argparse, base64, io, pathlib, re, sys, zipfile, urllib.request

ROOT   = pathlib.Path(__file__).resolve().parent
SRC, OUT  = ROOT / "src", ROOT / "assets"
ASRC, FONTS, CACHE = ROOT / "assets_src", ROOT / "fonts", ROOT / ".icon-cache"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
SVG_FILES = ["hero.svg", "about-life.svg", "stack.svg", "id-dashboard.svg", "connect.svg"]

FONTS_SPEC = {
    "SpaceGrotesk-Bold.woff2":  "https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@700&display=swap",
    "JetBrainsMono-Regular.woff2": "https://fonts.googleapis.com/css2?family=JetBrains+Mono&display=swap",
}
FONT_LICENSES = [
    ("OFL-spacegrotesk.txt",  "https://raw.githubusercontent.com/google/fonts/main/ofl/spacegrotesk/OFL.txt"),
    ("OFL-jetbrainsmono.txt", "https://raw.githubusercontent.com/google/fonts/main/ofl/jetbrainsmono/OFL.txt"),
]
SI_SLUGS = {
    "SI_PYTHON": ("python",), "SI_JAVASCRIPT": ("javascript",), "SI_TYPESCRIPT": ("typescript",),
    "SI_REACT": ("react",), "SI_NODEDOTJS": ("nodedotjs",), "SI_VITE": ("vite",),
    "SI_EXPRESS": ("express",), "SI_FLASK": ("flask",), "SI_KOTLIN": ("kotlin",),
    "SI_SQLITE": ("sqlite",), "SI_MYSQL": ("mysql",), "SI_MONGODB": ("mongodb",),
    "SI_AWS": ("amazonwebservices", "amazonaws"), "SI_DOCKER": ("docker",),
    "SI_GIT": ("git",), "SI_GITHUB": ("github",), "SI_OPENCV": ("opencv",),
    "SI_PANDAS": ("pandas",), "SI_SCIKITLEARN": ("scikitlearn",),
    "SI_TENSORFLOW": ("tensorflow",), "SI_PYTORCH": ("pytorch",),
    "SI_LINKEDIN": ("linkedin",), "SI_INSTAGRAM": ("instagram",),
}
CDNS = ("https://cdn.jsdelivr.net/npm/simple-icons@latest/icons/{s}.svg",
        "https://unpkg.com/simple-icons@latest/icons/{s}.svg")
# CC0 stand-ins, used only if every CDN fails:
FALLBACKS = {
    "SI_GITHUB": "M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12",
    "SI_LINKEDIN": "M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.225 0z",
}
GENERIC_FALLBACK = "M5 3h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2zm7 7a2 2 0 1 0 0 4 2 2 0 0 0 0-4z"

def http(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()

def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()

def ensure_fonts(no_fetch):
    FONTS.mkdir(exist_ok=True)
    (FONTS / "licenses").mkdir(exist_ok=True)
    for fname, css_url in FONTS_SPEC.items():
        p = FONTS / fname
        if p.exists():
            continue
        if no_fetch:
            sys.exit(f"[fonts] {fname} missing and --no-fetch given.")
        css = http(css_url).decode()
        latin = None
        for subset, body in re.findall(r"/\*\s*([a-z-]+)\s*\*/\s*@font-face\s*\{([^}]*)\}", css):
            if subset == "latin":
                latin = body
        if not latin:
            sys.exit(f"[fonts] latin subset not found for {fname}.")
        m = re.search(r"url\((https://[^)]+\.woff2)\)", latin)
        if not m:
            sys.exit(f"[fonts] no woff2 URL for {fname}.")
        p.write_bytes(http(m.group(1)))
        print(f"[fonts] downloaded {fname} ({p.stat().st_size // 1024} KB)")
    for fname, url in FONT_LICENSES:
        lp = FONTS / "licenses" / fname
        if lp.exists():
            continue
        try:
            lp.write_bytes(http(url))
        except Exception as e:
            print(f"[fonts] license fetch failed ({fname}): {e}\n        add manually: {url}")

def icon_path(slugs):
    for s in slugs:
        for cdn in CDNS:
            try:
                svg = http(cdn.format(s=s)).decode()
            except Exception:
                continue
            ds = re.findall(r'\sd="([^"]+)"', svg)
            if ds:
                return " ".join(ds), s
    return None, None

def fetch_icons(no_fetch):
    CACHE.mkdir(exist_ok=True)
    out, missing = {}, []
    for token, slugs in SI_SLUGS.items():
        cache = CACHE / (slugs[0] + ".d")
        if cache.exists():
            out[token] = cache.read_text()
            continue
        d = slug = None
        if not no_fetch:
            d, slug = icon_path(slugs)
        if d:
            cache.write_text(d)
            out[token] = d
            print(f"[icons] {slug}: fetched")
        else:
            missing.append(slugs[0])
            out[token] = FALLBACKS.get(token, GENERIC_FALLBACK)
    if missing:
        print(f"[icons] WARNING - fallback glyphs used for: {', '.join(missing)}")
    return out

def optimize_png(src: pathlib.Path, max_w: int) -> bytes:
    raw = src.read_bytes()
    try:
        from PIL import Image
    except ImportError:
        print(f"[photos] Pillow not installed - embedding {src.name} at original size")
        return raw
    im = Image.open(io.BytesIO(raw))
    if im.mode != "RGBA":
        im = im.convert("RGBA")
    if im.width > max_w:
        im = im.resize((max_w, round(im.height * max_w / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    out = buf.getvalue()
    print(f"[photos] {src.name}: {len(raw)//1024} KB -> {len(out)//1024} KB (alpha kept)")
    return out if len(out) < len(raw) else raw

def verify(name, t):
    errs = []
    if "{{" in t:
        errs.append("unreplaced token remains")
    for attr in ("href", "xlink:href", "src"):
        for m in re.finditer(attr + r'\s*=\s*"([^"]*)"', t):
            v = m.group(1)
            if v and not v.startswith(("data:", "#", "url(")):
                errs.append(f"non-local {attr}: {v[:60]}")
    if re.search(r"<\s*(script|foreignObject)", t, re.I):
        errs.append("script/foreignObject found")
    ids = re.findall(r'\sid="([^"]+)"', t)
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        errs.append(f"duplicate ids: {dup}")
    return errs

def make_zip():
    zpath = ROOT / "upload-me.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        readme = ROOT / "README.md"
        if readme.exists():
            z.write(readme, "README.md")
        else:
            print("[zip] README.md not found - skipped (save it from the delivery first!)")
        for f in SVG_FILES:
            z.write(OUT / f, f"assets/{f}")
        lic = FONTS / "licenses"
        if lic.exists():
            for lf in sorted(lic.glob("*.txt")):
                z.write(lf, f"assets/licenses/{lf.name}")
    print(f"[zip] wrote {zpath}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-fetch", action="store_true")
    args = ap.parse_args()
    for p in (ASRC / "id.png", ASRC / "right_pointing.png"):
        if not p.exists():
            sys.exit(f"[photos] missing {p}\n  Save the two images you attached (portrait + pointing pose)\n  into assets_src/ with those exact names, then re-run.")
    OUT.mkdir(exist_ok=True)
    ensure_fonts(args.no_fetch)
    icons = fetch_icons(args.no_fetch)
    tokens = {
        "{{PORTRAIT}}": "data:image/png;base64," + b64(optimize_png(ASRC / "id.png", 560)),
        "{{POINTING}}": "data:image/png;base64," + b64(optimize_png(ASRC / "right_pointing.png", 700)),
        "{{FONT_DISPLAY}}": b64((FONTS / "SpaceGrotesk-Bold.woff2").read_bytes()),
        "{{FONT_MONO}}": b64((FONTS / "JetBrainsMono-Regular.woff2").read_bytes()),
    }
    tokens.update(icons)
    ok = True
    for name in SVG_FILES:
        t = (SRC / name).read_text(encoding="utf-8")
        for k, v in tokens.items():
            t = t.replace(k, v)
        (OUT / name).write_text(t, encoding="utf-8")
        errs = verify(name, t)
        print(f"[svg] {name:18s} {(OUT / name).stat().st_size / 1024:8.1f} KB  {'OK' if not errs else 'FAIL'}")
        for e in errs:
            ok = False
            print(f"        - {e}")
    if not ok:
        sys.exit("[build] verification failed - fix above.")
    make_zip()
    print("\nDone. Open preview.html for the visual QA pass, then upload README.md + assets/ (or just push upload-me.zip contents).")

if __name__ == "__main__":
    main()
