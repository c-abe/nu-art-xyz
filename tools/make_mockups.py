#!/usr/bin/env python3
"""作品画像をインテリア写真の額の中に合成して、作品ごとのモックアップ一式を作る。

使い方:
    python3 tools/make_mockups.py            # 全作品を生成
    python3 tools/make_mockups.py grape_A4   # 指定した作品だけ生成

新しい作品を images/ に置いて index.html の WORKS に足したら、
このスクリプトを流すだけでモックアップ5枚が揃う。

額の四隅 (SCENES) は、既存モックアップ25枚の差分から自動抽出した実測値。
cut2 は額が傾いているので射影変換で貼る。cut3 は額が2つあるので、
大きい方に対象作品、小さい方に隣の作品を入れてギャラリーウォールに見せる。
"""
import json
import os
import re
import sys

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGES = os.path.join(ROOT, "images")
SCENE_DIR = os.path.join(IMAGES, "mockups")
OUT_DIR = os.path.join(IMAGES, "scenes")

# 各シーンの下地と、額の内側四隅 (左上→右上→右下→左下)。
# quads が2つあるシーンは [主, 副] の順。
SCENES = {
    1: {
        "base": "women01_cut1.jpg",
        "quads": [[[326, 139], [671, 144], [671, 629], [329, 629]]],
    },
    2: {
        "base": "women01_cut2.jpg",
        "quads": [[[552, 191], [1022, 202], [1006, 930], [535, 920]]],
    },
    3: {
        "base": "women01_cut3.jpg",
        "quads": [
            [[605, 324], [793, 324], [793, 576], [604, 576]],
            [[380, 339], [541, 340], [541, 569], [380, 571]],
        ],
    },
    4: {
        "base": "women01_cut4.jpg",
        "quads": [[[303, 273], [896, 272], [896, 1138], [304, 1139]]],
    },
    5: {
        "base": "women01_cut5.jpg",
        "quads": [[[304, 273], [897, 272], [896, 1136], [304, 1139]]],
    },
}

SCENE_BG = os.path.join(IMAGES, "scene_bg")

CUTS = 5             # 1作品あたりの枚数
OUT_WIDTH = 1100      # 書き出す横幅
WEBP_QUALITY = 78
PAPER = (250, 249, 246)   # 紙の白（BGR）。額に対して作品の比率が違うときの余白。


def load_scenes():
    """既存モックアップ由来の5つと、PSD から取り出したものを1つの並びにする。

    SCENES は images/mockups/ の完成画像を下地にしていて、額の中には
    まだ women01 の作品が写っている。四隅を丸ごと上書きするので問題ない。
    images/scene_bg/ の方は PSD から作品と透かしを外して書き出した空の額。
    """
    out = []
    for n, spec in SCENES.items():
        out.append({"id": f"cut{n}", "base": os.path.join(SCENE_DIR, spec["base"]),
                    "quads": spec["quads"]})
    man = os.path.join(SCENE_BG, "scenes.json")
    if os.path.exists(man):
        for name, spec in json.load(open(man, encoding="utf-8")).items():
            out.append({"id": name, "base": os.path.join(SCENE_BG, spec["bg"]),
                        "quads": spec["quads"]})
    return out


def load_works():
    """index.html の WORKS 配列から (ファイル名, 作品名) を読む。

    サイトの表示順と生成順を常に一致させるため、データ源は index.html 一本に絞る。
    """
    html = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
    rows = re.findall(r'\{f:"([^"]+)",\s*t:"([^"]*)"', html)
    if not rows:
        raise SystemExit("index.html から WORKS を読めませんでした")
    return rows


def expand(quad, px=3):
    """額の内側をわずかに外へ広げる。下地の古い作品が縁に残らないようにするため。"""
    q = np.array(quad, dtype=np.float64)
    c = q.mean(axis=0)
    out = []
    for p in q:
        v = p - c
        n = np.linalg.norm(v)
        out.append(p + v / n * px if n else p)
    return np.array(out, dtype=np.float32)


def fit_to_paper(art, w, h):
    """作品を w x h の紙に収める。はみ出さないよう contain、余白は紙の白。"""
    canvas = np.full((h, w, 3), PAPER, np.uint8)
    ah, aw = art.shape[:2]
    s = min(w / aw, h / ah)
    nw, nh = max(1, int(round(aw * s))), max(1, int(round(ah * s)))
    interp = cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC
    r = cv2.resize(art, (nw, nh), interpolation=interp)
    canvas[(h - nh) // 2:(h - nh) // 2 + nh, (w - nw) // 2:(w - nw) // 2 + nw] = r
    return canvas


def paste(scene, art, quad):
    """作品を額の四隅へ射影変換で貼り込む。"""
    dst = expand(quad)
    w = int(round(max(np.linalg.norm(dst[1] - dst[0]), np.linalg.norm(dst[2] - dst[3]))))
    h = int(round(max(np.linalg.norm(dst[3] - dst[0]), np.linalg.norm(dst[2] - dst[1]))))
    paper = fit_to_paper(art, w, h)
    src = np.array([[0, 0], [w, 0], [w, h], [0, h]], np.float32)
    M = cv2.getPerspectiveTransform(src, dst)
    sh, sw = scene.shape[:2]
    warped = cv2.warpPerspective(paper, M, (sw, sh), flags=cv2.INTER_CUBIC)
    mask = np.zeros((sh, sw), np.uint8)
    cv2.fillConvexPoly(mask, dst.astype(np.int32), 255)
    # 縁を1px ぼかして、額の内側との境目を馴染ませる
    mask = cv2.GaussianBlur(mask, (3, 3), 0)
    a = (mask.astype(np.float32) / 255.0)[..., None]
    return (warped * a + scene * (1 - a)).astype(np.uint8)


def read_art(fname):
    path = os.path.join(IMAGES, fname)
    art = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if art is None:
        raise SystemExit(f"読めません: {path}")
    if art.ndim == 3 and art.shape[2] == 4:      # PNG の透過は白で埋める
        alpha = art[:, :, 3:4].astype(np.float32) / 255.0
        art = (art[:, :, :3] * alpha + np.array(PAPER) * (1 - alpha)).astype(np.uint8)
    elif art.ndim == 2:
        art = cv2.cvtColor(art, cv2.COLOR_GRAY2BGR)
    return art


def main():
    works = load_works()
    only = sys.argv[1] if len(sys.argv) > 1 else None
    os.makedirs(OUT_DIR, exist_ok=True)

    scenes = load_scenes()
    for s in scenes:
        s["img"] = cv2.imread(s["base"])
        if s["img"] is None:
            raise SystemExit(f"シーン画像がありません: {s['base']}")
    print(f"シーン {len(scenes)} 種類")

    arts = [read_art(f) for f, _ in works]
    made = 0
    manifest = {}

    for i, (fname, title) in enumerate(works):
        # 作品ごとにシーンの取り始めをずらし、隣り合う作品が
        # 同じ並びにならないようにする。順番は作品番号から決まるので毎回同じ。
        chosen = [scenes[(i * 3 + k) % len(scenes)] for k in range(CUTS)]
        if only and only not in fname:
            continue
        cuts = []
        for n, spec in enumerate(chosen, 1):
            out = spec["img"].copy()
            for j, quad in enumerate(spec["quads"]):
                # 副の額には隣の作品を入れて、壁に複数飾っている見え方にする
                art = arts[i] if j == 0 else arts[(i + 1) % len(arts)]
                out = paste(out, art, quad)
            if out.shape[1] != OUT_WIDTH:
                h = int(round(out.shape[0] * OUT_WIDTH / out.shape[1]))
                out = cv2.resize(out, (OUT_WIDTH, h), interpolation=cv2.INTER_AREA)
            rel = f"{i + 1:02d}_{n}.webp"
            cv2.imwrite(os.path.join(OUT_DIR, rel), out,
                        [cv2.IMWRITE_WEBP_QUALITY, WEBP_QUALITY])
            cuts.append(rel)
            made += 1
        manifest[f"{i + 1:02d}"] = {"file": fname, "title": title,
                                    "cuts": cuts,
                                    "scenes": [c["id"] for c in chosen]}

    if not only:
        with open(os.path.join(OUT_DIR, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=1)

    total = sum(os.path.getsize(os.path.join(OUT_DIR, f))
                for f in os.listdir(OUT_DIR) if f.endswith(".webp"))
    print(f"生成 {made} 枚 / 合計 {total / 1e6:.1f} MB -> images/scenes/")


if __name__ == "__main__":
    main()
