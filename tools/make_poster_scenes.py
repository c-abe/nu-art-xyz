#!/usr/bin/env python3
"""額のないポスター型モックPSDから、A/B判の下地を作る。

使い方（PSDが大きいので1枚ずつ）:
    python3 tools/make_poster_scenes.py Portrait
    python3 tools/make_poster_scenes.py Landscape
    python3 tools/make_poster_scenes.py Mockup

このPSDのポスター面は 0.595〜0.641 で、作品の 1:√2（0.707）と合わない。
そのままでは端を1〜2割切ることになるので、面のほうを 1:√2 に組み直す。

壁に貼る2枚（Portrait / Landscape）は下地に影が焼き込まれていないので、
面の大きさを変えたうえで影をこちらで描く。
立てかけの1枚（Mockup）は枠が下地に焼き込まれているため形は変えられない。
枠の内側に 1:√2 で収め、余った分は細い余白として残す。
"""
import json
import os
import sys
import warnings

warnings.filterwarnings("ignore")

import cv2
import numpy as np
from psd_tools import PSDImage

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "images", "scene_bg")
PSD_DIR = os.environ.get(
    "MOCK_PSD_DIR",
    os.path.expanduser("~/Desktop/AIの作業場/nu-art/素材/モックPSD"))

RATIO = 1 / (2 ** 0.5)
OUT_W = 1400

# reshape : 面を 1:√2 に作り直してよいか（下地に枠や影が焼かれていないか）
# light   : 光の来る向き。影はこの反対側へ落とす
SPECS = {
    "Portrait":  {"key": "poster_bed_tall",  "reshape": True,
                  "light": (0.0, -1.0), "soft": 0.045, "crop": (0.12, 0.00, 0.88, 0.92)},
    "Landscape": {"key": "poster_bed_wide",  "reshape": True,
                  "light": (0.0, -1.0), "soft": 0.045, "crop": (0.10, 0.00, 0.90, 0.92)},
    "Mockup":    {"key": "poster_lean_tall", "reshape": False,
                  "light": (1.0, -0.4), "soft": 0.0,   "crop": (0.05, 0.02, 0.95, 0.86)},
}


def poster_rect(psd):
    """印刷面の位置を返す。Main Layers の中の Poster が実際の面。"""
    for l in psd.descendants():
        if l.kind == "smartobject" and l.name == "Poster":
            return [int(v) for v in l.bbox]
    raise SystemExit("Poster レイヤーが見つかりません")


def to_ab(rect, reshape):
    """面を 1:√2 にする。中心はそのまま。"""
    x0, y0, x1, y1 = rect
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    w, h = x1 - x0, y1 - y0
    tall = h >= w
    if reshape:
        # 長いほうの辺を保って、短いほうを 1:√2 に合わせる
        if tall:
            w = h * RATIO
        else:
            h = w * RATIO
    else:
        # 枠の内側に収める。はみ出させない
        if (w / h if tall else h / w) > RATIO:
            w, h = (h * RATIO, h) if tall else (w, w * RATIO)
        else:
            w, h = (w, w / RATIO) if tall else (h / RATIO, h)
    return [int(cx - w / 2), int(cy - h / 2), int(cx + w / 2), int(cy + h / 2)]


def shadow(canvas, rect, light, soft):
    """面の外側に落ちる影。下地に影がないぶん、これがないと貼り付いて見える。"""
    x0, y0, x1, y1 = rect
    m = np.zeros(canvas.shape[:2], np.float32)
    m[y0:y1, x0:x1] = 1.0
    k = max(3, int(soft * (y1 - y0)) | 1)
    m = cv2.GaussianBlur(m, (k, k), 0)
    dx = int(-light[0] * soft * (y1 - y0) * 0.5)
    dy = int(-light[1] * soft * (y1 - y0) * 0.5)
    m = np.roll(np.roll(m, dy, axis=0), dx, axis=1)
    m[y0:y1, x0:x1] = 0                       # 面の内側は暗くしない
    return canvas * (1 - (m * 0.34)[..., None])


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else None
    if name not in SPECS:
        raise SystemExit("使い方: make_poster_scenes.py " + " | ".join(SPECS))
    spec = SPECS[name]

    psd = PSDImage.open(os.path.join(PSD_DIR, name + ".psd"))
    base = [l for l in psd.descendants() if l.name == "Base"][0]
    img = np.array(base.composite(force=True).convert("RGB"))[:, :, ::-1].astype(np.float32)

    rect = to_ab(poster_rect(psd), spec["reshape"])
    if spec["soft"] > 0:
        img = shadow(img, rect, spec["light"], spec["soft"])
    # 面は紙の白で塗っておく。あとで作品を貼り込む
    img[rect[1]:rect[3], rect[0]:rect[2]] = (250, 249, 246)
    img = np.clip(img, 0, 255).astype(np.uint8)

    H, W = img.shape[:2]
    l, t, r, b = spec["crop"]
    x0, y0, x1, y1 = int(l * W), int(t * H), int(r * W), int(b * H)
    img = img[y0:y1, x0:x1]
    rect = [rect[0] - x0, rect[1] - y0, rect[2] - x0, rect[3] - y0]

    s = OUT_W / img.shape[1]
    img = cv2.resize(img, (OUT_W, int(img.shape[0] * s)), interpolation=cv2.INTER_AREA)
    rect = [int(round(v * s)) for v in rect]
    quad = [[rect[0], rect[1]], [rect[2], rect[1]], [rect[2], rect[3]], [rect[0], rect[3]]]

    os.makedirs(OUT, exist_ok=True)
    key = spec["key"]
    cv2.imwrite(os.path.join(OUT, key + ".jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 90])

    man = os.path.join(OUT, "scenes.json")
    sc = json.load(open(man, encoding="utf-8")) if os.path.exists(man) else {}
    sc[key] = {"bg": key + ".jpg", "size": [img.shape[1], img.shape[0]],
               "quads": [quad], "src": name + ".psd（印刷面を A/B判に組み直し）"}
    json.dump(sc, open(man, "w"), ensure_ascii=False, indent=1)

    w, h = rect[2] - rect[0], rect[3] - rect[1]
    print(f"{key:18} {img.shape[1]}x{img.shape[0]}  印刷面 {w}x{h} "
          f"比 {min(w,h)/max(w,h):.3f}")


if __name__ == "__main__":
    main()
