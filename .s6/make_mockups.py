#!/usr/bin/env python3
"""作品画像をインテリア写真の額の中に合成して、作品ごとのモックアップ一式を作る。

使い方:
    python3 tools/make_mockups.py            # 全作品を生成
    python3 tools/make_mockups.py grape_A4   # 指定した作品だけ生成

新しい作品を images/ に置いて index.html の WORKS に足したら、
このスクリプトを流すだけでモックアップが揃う。

作品と額の向きは合わせる。横長の作品を縦の額に入れると
上下に大きな余白ができて額装として不自然なので、
横長の作品は横向きの額を持つシーンからだけ選ぶ。

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

# 下地はすべて images/scene_bg/ にある。scenes.json に額の内側四隅と、
# その額が何判の作品用か（print）が入っている。
#
# 以前は既存モックアップの1枚（women01_cut1.jpg）も混ぜていたが、
# 額の大きさが変えられず、A4 も B3 も同じ大きさに見えてしまうので外した。
SCENE_BG = os.path.join(IMAGES, "scene_bg")

CUTS = 5             # 1作品あたりの枚数
OUT_WIDTH = 1100      # 書き出す横幅
WEBP_QUALITY = 78
PAPER = (250, 249, 246)   # 紙の白（BGR）。額に対して作品の比率が違うときの余白。


def photo_of(scene_id):
    """シーン名から元の写真を取り出す。white_ledge_a_tall_A4 → white_ledge。

    同じ写真から作った別バージョンを、1作品の中で重ねて使わないための判定。
    """
    name = re.sub(r"_(A4|B4|A3|B3)$", "", scene_id)
    name = re.sub(r"_(tall|wide)$", "", name)
    return re.sub(r"_[ab]$", "", name)


def orient(quad):
    """額の向きを返す。作品と額の向きを合わせるために使う。"""
    p = np.array(quad, dtype=float)
    w = max(np.linalg.norm(p[1] - p[0]), np.linalg.norm(p[2] - p[3]))
    h = max(np.linalg.norm(p[3] - p[0]), np.linalg.norm(p[2] - p[1]))
    return "wide" if w / h > 1.15 else "tall"


def load_scenes():
    """下地の一覧を作る。額の向きと、何判の作品用かを持たせる。"""
    out = []
    man = os.path.join(SCENE_BG, "scenes.json")
    for name, spec in json.load(open(man, encoding="utf-8")).items():
        out.append({"id": name, "base": os.path.join(SCENE_BG, spec["bg"]),
                    "quads": spec["quads"], "o": orient(spec["quads"][0]),
                    "print": spec.get("print", "B3")})
    return out


# シリーズごとに決まった部屋を使う。
# TOPには各作品の1カット目を並べるので、同じシリーズは同じ部屋・同じ額で揃い、
# シリーズが変われば部屋も額の色も変わる。並べたときに区切りが読める。
# 並ぶ順（small world → inside1 → Collage → inside2 → girls → Beautiful Women）で
# 部屋が黄土→白→灰緑と回るようにしてある。同じ部屋の行が隣り合うと区切りが読めない。
SERIES_SCENE = {
    "small world":     "ochre_sofa_a",    # 黄土の壁・濃い木
    "inside1":         "white_ledge_a",   # 白壁・濃い木
    "Collage":         "green_sofa_a",    # 灰緑の壁・濃い木
    "inside2":         "ochre_sofa_b",    # 黄土の壁・黒額
    "girls":           "white_ledge_b",   # 白壁・黒額
    "Beautiful Women": "green_sofa_b",    # 灰緑の壁・オーク
}


# 1カット目のあとに必ず入れる部屋。シリーズごとの指定。
# 額のないポスター型を混ぜたいシリーズにだけ書く。
SERIES_EXTRA = {
    "Beautiful Women": ["poster_bed"],
}


def load_works():
    """index.html の WORKS 配列から (ファイル名, 作品名, シリーズ, 判型) を読む。

    サイトの表示順と生成順を常に一致させるため、データ源は index.html 一本に絞る。
    判型は詳細に出しているサイズそのもの。部屋に置く額の大きさもこれで決まる。
    """
    html = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
    rows = [(f, t, sr, sz.split()[0]) for f, t, sz, sr in
            re.findall(r'\{f:"([^"]+)",\s*t:"([^"]*)".*?sz:"([^"]+)".*?sr:"([^"]+)"', html)]
    if not rows:
        raise SystemExit("index.html から WORKS を読めませんでした")
    unknown = {s for _, _, s, _ in rows} - set(SERIES_SCENE)
    if unknown:
        raise SystemExit("部屋を決めていないシリーズ: " + ", ".join(unknown))
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


# 額と作品の比率がこれ以内なら、はみ出す分を切って額いっぱいに入れる。
# 余白を残すと、傾いた額では白帯が斜めに走って額装が歪んで見える。
COVER_TOLERANCE = 1.32


def fit_to_paper(art, w, h):
    """作品を w x h の額の中に入れる。

    比率が近ければ cover（少し切って隙間なく）。
    大きく違うときだけ contain にして、余った所は紙の白で埋める。
    """
    ah, aw = art.shape[:2]
    fit  = min(w / aw, h / ah)          # 収める
    fill = max(w / aw, h / ah)          # 埋める
    fit_to_paper.matted = getattr(fit_to_paper, "matted", 0)
    if fill / fit <= COVER_TOLERANCE:
        nw, nh = max(w, int(round(aw * fill))), max(h, int(round(ah * fill)))
        r = cv2.resize(art, (nw, nh),
                       interpolation=cv2.INTER_AREA if fill < 1 else cv2.INTER_CUBIC)
        x, y = (nw - w) // 2, (nh - h) // 2
        return r[y:y + h, x:x + w]

    fit_to_paper.matted += 1
    canvas = np.full((h, w, 3), PAPER, np.uint8)
    nw, nh = max(1, int(round(aw * fit))), max(1, int(round(ah * fit)))
    r = cv2.resize(art, (nw, nh),
                   interpolation=cv2.INTER_AREA if fit < 1 else cv2.INTER_CUBIC)
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


def neighbour(arts, i, want):
    """i の次にある、向きの合う作品を返す。無ければ i の次をそのまま返す。"""
    n = len(arts)
    for k in range(1, n):
        a = arts[(i + k) % n]
        h, w = a.shape[:2]
        if ("wide" if w > h else "tall") == want:
            return (i + k) % n
    return (i + 1) % n


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

    arts = [read_art(f) for f, _, _, _ in works]
    # 額の向きと、作品の判型が合う下地だけを使う
    pool = {(o, sz): [s for s in scenes if s["o"] == o and s["print"] == sz]
            for o in ("tall", "wide")
            for sz in {w[3] for w in works}}
    for k, v in sorted(pool.items()):
        print("  %-5s %-3s %d室" % (k[0], k[1], len(v)))
    made = 0
    manifest = {}

    by_id = {s["id"]: s for s in scenes}

    for i, (fname, title, series, psize) in enumerate(works):
        ah, aw = arts[i].shape[:2]
        want_o = "wide" if aw > ah else "tall"
        p = pool[(want_o, psize)] or pool[("tall", psize)]
        # 1カット目はシリーズの部屋で固定。TOPに並べたとき同じシリーズが揃う。
        suffix = "" if psize == "B3" else f"_{psize}"
        head = by_id.get(f"{SERIES_SCENE[series]}_{want_o}{suffix}")
        if head is None:
            raise SystemExit(f"{series} の {want_o} の部屋がありません")
        # 2カット目以降は残りから。作品ごとに取り始めをずらして並びを変える。
        # ただし同じ部屋は1作品に1枚まで。white_ledge_a と white_ledge_b は
        # 額の色と寄りが違うだけで同じ写真なので、並ぶと使い回しに見える。
        rest = [s for s in p if photo_of(s["id"]) != photo_of(head["id"])]
        seen = {photo_of(head["id"])}
        chosen = [head]
        # シリーズで指定された部屋を先に入れる
        for want in SERIES_EXTRA.get(series, []):
            c = by_id.get(f"{want}_{want_o}{suffix}") or by_id.get(want)
            if c is not None and c["o"] == want_o and photo_of(c["id"]) not in seen:
                seen.add(photo_of(c["id"]))
                chosen.append(c)
        for k in range(len(rest)):
            c = rest[(i * 3 + k) % len(rest)]
            if photo_of(c["id"]) in seen:
                continue
            seen.add(photo_of(c["id"]))
            chosen.append(c)
            if len(chosen) == CUTS:
                break
        if only and only not in fname:
            continue
        cuts = []
        for n, spec in enumerate(chosen, 1):
            out = spec["img"].copy()
            for j, quad in enumerate(spec["quads"]):
                if j == 0:
                    art = arts[i]
                else:
                    # 副の額にも隣の作品を入れて、壁に複数飾っている見え方にする。
                    # ただし向きの合うものを選ぶ。横長を縦の額に入れると余白が出る。
                    art = arts[neighbour(arts, i, orient(quad))]
                out = paste(out, art, quad)
            if out.shape[1] != OUT_WIDTH:
                h = int(round(out.shape[0] * OUT_WIDTH / out.shape[1]))
                out = cv2.resize(out, (OUT_WIDTH, h), interpolation=cv2.INTER_AREA)
            rel = f"{i + 1:02d}_{n}.webp"
            cv2.imwrite(os.path.join(OUT_DIR, rel), out,
                        [cv2.IMWRITE_WEBP_QUALITY, WEBP_QUALITY])
            cuts.append(rel)
            made += 1
        manifest[f"{i + 1:02d}"] = {"file": fname, "title": title, "series": series,
                                    "orient": want_o, "cuts": cuts,
                                    "scenes": [c["id"] for c in chosen]}

    if not only:
        with open(os.path.join(OUT_DIR, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=1)

    total = sum(os.path.getsize(os.path.join(OUT_DIR, f))
                for f in os.listdir(OUT_DIR) if f.endswith(".webp"))
    matted = getattr(fit_to_paper, "matted", 0)
    print(f"生成 {made} 枚 / 合計 {total / 1e6:.1f} MB -> images/scenes/")
    print(f"  額いっぱい {made - matted} 枚 / 余白つき {matted} 枚")
    if matted and not only:
        # 余白が入ると、傾いた額では白帯が斜めに走って額装が歪んで見える。
        # 出たら黙って通さず、気づけるようにする。
        print("  ※ 余白が出ています。額と作品の向きか比率が合っていません。")


if __name__ == "__main__":
    main()
