#!/usr/bin/env python3
"""白背景の額モックアップを、壁に掛かっている見た目に作り直す。

Wallderful の PSD から額と影だけを抜き、自前で作った壁のテクスチャに載せる。
PSD をそのまま平面化すると、乗算で重ねてあるグループが不透明に描かれて
濃い塊になってしまうので、必要なレイヤーだけを指定して描いている。

    python3 tools/make_wall_scene.py
"""
import json
import os
import warnings

warnings.filterwarnings("ignore")

import cv2
import numpy as np
from psd_tools import PSDImage

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "images", "scene_bg")
PSD = os.environ.get(
    "MOCK_PSD_DIR",
    os.path.expanduser("~/Desktop/AIの作業場/nu-art/素材/モックPSD"),
)
SRC = os.path.join(PSD, "Wallderful horizontal freebie2.psd")

CANVAS = (1400, 1050)          # 書き出す大きさ
WALL   = (232, 231, 228)       # 壁の色（BGR）。少し暖かい灰白。


def descend(layers):
    for l in layers:
        yield l
        if l.is_group():
            yield from descend(l)


def frame_with_alpha():
    """額とその影だけを、背景なしで描いて返す。"""
    psd = PSDImage.open(SRC)
    for l in descend(psd):
        l.visible = False
    # 11"x14" の額とその影だけを出す。同名レイヤーが他のサイズにもあるので
    # bbox で本体を見分ける。
    want = {("Frame Shadows", (915, 485, 3324, 2479)),
            ("Frame texture # 1", (960, 531, 3243, 2374))}
    for l in descend(psd):
        if (l.name, tuple(l.bbox)) in want:
            l.visible = True
            node = l.parent
            while node is not None and node is not psd:
                node.visible = True
                node = node.parent
    img = psd.composite(force=True)
    a = np.array(img.convert("RGBA"))
    ys, xs = np.where(a[:, :, 3] > 8)
    return a[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def wall(w, h):
    """塗り壁のような下地を作る。

    平らな白のままだと、切り抜いた額が浮いて紙の上に置いたように見える。
    細かいざらつきと、上から回り込む光のむらを入れて面を感じさせる。
    """
    rng = np.random.default_rng(7)
    base = np.full((h, w, 3), WALL, np.float32)

    # ざらつき。粗い斑と細かい粒を重ねる
    coarse = rng.normal(0, 1, (h // 8 + 1, w // 8 + 1)).astype(np.float32)
    coarse = cv2.resize(coarse, (w, h), interpolation=cv2.INTER_CUBIC)
    coarse = cv2.GaussianBlur(coarse, (0, 0), 3)
    fine = rng.normal(0, 1, (h, w)).astype(np.float32)
    grain = (coarse * 4.5 + fine * 1.6)[..., None]

    # 光。左上がやや明るく、隅が落ちる
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    light = 1.0 - 0.16 * ((xx / w) * 0.6 + (yy / h) * 0.8)
    r = np.hypot(xx / w - 0.5, yy / h - 0.5)
    light *= 1.0 - 0.14 * np.clip(r / 0.7, 0, 1) ** 2

    out = base * light[..., None] + grain
    return np.clip(out, 0, 255).astype(np.uint8)


def inner_quad(img):
    """額の内側（作品が入る面）の四隅を返す。

    額の中は一色で塗り潰されているので、中心の色に近い画素をまとめて拾う。
    額そのものも影も色が違うので、開口部だけが残る。
    """
    rgb = img[:, :, :3].astype(np.int16)
    hh, ww = rgb.shape[:2]
    centre = rgb[hh // 2, ww // 2]
    hole = (np.abs(rgb - centre).sum(axis=2) < 30).astype(np.uint8) * 255
    hole = cv2.morphologyEx(hole, cv2.MORPH_OPEN, np.ones((11, 11), np.uint8))
    cnts, _ = cv2.findContours(hole, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        raise SystemExit("額の内側を見つけられませんでした")
    c = max(cnts, key=cv2.contourArea)
    peri = cv2.arcLength(c, True)
    ap = cv2.approxPolyDP(c, 0.02 * peri, True)
    if len(ap) != 4:
        ap = cv2.boxPoints(cv2.minAreaRect(c)).astype(np.int32).reshape(-1, 1, 2)
    pts = ap.reshape(4, 2).astype(float)
    s, d = pts.sum(1), np.diff(pts, axis=1).ravel()
    order = [pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]]
    return [[round(float(x)), round(float(y))] for x, y in order]


def main():
    fr = frame_with_alpha()

    W, H = CANVAS
    scale = min(W * 0.72 / fr.shape[1], H * 0.78 / fr.shape[0])
    nw, nh = int(fr.shape[1] * scale), int(fr.shape[0] * scale)
    fr = cv2.resize(fr, (nw, nh), interpolation=cv2.INTER_AREA)

    bg = wall(W, H)
    x0, y0 = (W - nw) // 2, (H - nh) // 2
    roi = bg[y0:y0 + nh, x0:x0 + nw].astype(np.float32)
    al = (fr[:, :, 3:4].astype(np.float32) / 255.0)
    bg[y0:y0 + nh, x0:x0 + nw] = (fr[:, :, :3] * al + roi * (1 - al)).astype(np.uint8)

    # 合成し終えた絵から内側を取る。途中で拡大縮小を挟むとズレるため。
    quad = inner_quad(bg)

    os.makedirs(OUT, exist_ok=True)
    cv2.imwrite(os.path.join(OUT, "frame_wide.jpg"), bg,
                [cv2.IMWRITE_JPEG_QUALITY, 90])

    man = os.path.join(OUT, "scenes.json")
    sc = json.load(open(man, encoding="utf-8")) if os.path.exists(man) else {}
    sc["frame_wide"] = {"bg": "frame_wide.jpg", "size": [W, H], "quads": [quad],
                        "src": "Wallderful horizontal freebie2.psd（額と影のみ／壁は自前）"}
    sc.pop("plain_wide", None)          # 額のない白背景は使わない
    json.dump(sc, open(man, "w"), ensure_ascii=False, indent=1)
    print(f"frame_wide {W}x{H}  額の内側 {quad}")
    print("plain_wide は削除（額がないため）")


if __name__ == "__main__":
    main()
