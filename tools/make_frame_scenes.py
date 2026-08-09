#!/usr/bin/env python3
"""実際の部屋の写真に、A/B判の額を合成してモックアップの下地を作る。

作品は40点すべて 1:√2（A4・B4・B2・B1 共通の比）だが、
手持ちの額モックアップは米国判で作られていて内側の比が合わず、
そのままだと作品を1〜2割切らないと収まらなかった。

そこで木枠の縁だけを取り出し、角の造形を保ったまま伸ばして
（9スライス）内側がちょうど 1:√2 になる額を組み直す。
それを部屋の写真に、その写真の光に合わせた影をつけて置く。

    python3 tools/make_frame_scenes.py
"""
import json
import os
import warnings

warnings.filterwarnings("ignore")

import cv2
import numpy as np
from psd_tools import PSDImage

ROOT   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT    = os.path.join(ROOT, "images", "scene_bg")
ASSETS = os.environ.get(
    "NU_ASSETS", os.path.expanduser("~/Desktop/AIの作業場/nu-art/素材"))
PSD_DIR   = os.path.join(ASSETS, "モックPSD")
PHOTO_DIR = os.path.join(ASSETS, "フレーム写真")

RATIO = 1 / (2 ** 0.5)          # 1:√2。A判・B判に共通

# 判型ごとの長辺（mm）。額の大きさはこれに比例させる。
# いちばん大きい B3 を今までの見え方に合わせ、小さい判はその実寸比で縮める。
# こうしないと A4 も B3 も部屋の中で同じ大きさに見えて、値段の差が伝わらない。
SIZES = {"A4": 297, "B4": 364, "A3": 420, "B3": 515}
ANCHOR = "B3"
OUT_W = 1400                    # 書き出す横幅
OUT_ASPECT = 4 / 3              # 6種類とも同じ比。TOPで4枚ずつ隙間なく並べるため

# 部屋の写真ごとの置き方。
#   crop  : 元写真から使う範囲（左, 上, 右, 下／画像比）
#   at    : 額の中心（切り抜き後の比）
#   height: 額の高さ（切り抜き後の高さに対する比）
#   light : 光が来る向き。影はこの反対側に落とす
#   soft  : 影のぼかし量（額の高さに対する比）
#   finish: 額の仕上げ。wood=そのまま / oak=明るい木 / black=黒
#
# シリーズごとに違う部屋を割り当てたいので、写真3枚から
# 「位置と額の色を変えた2通り」ずつ、計6種類を作る。
PHOTOS = {
    # 棚（高さ約6割）の上の壁に掛ける。右の小物は残す。
    "white_ledge_a": {
        "file": "karim-manjra-mHcSOxitJqo-unsplash.jpg",
        "crop": (0.10, 0.04, 0.74, 0.94),
        "at": (0.40, 0.37), "height": 0.58, "finish": "wood",
        "light": (-0.3, -1.0), "soft": 0.048, "lift": 1.00,
    },
    "white_ledge_b": {
        "file": "karim-manjra-mHcSOxitJqo-unsplash.jpg",
        "crop": (0.12, 0.04, 0.80, 0.92),
        "at": (0.50, 0.36), "height": 0.58, "finish": "black",
        "light": (-0.3, -1.0), "soft": 0.052, "lift": 1.00,
    },
    # ソファ（高さ約6割）の上。右上のランプが光源。
    "ochre_sofa_a": {
        "file": "josh-sorenson-OxyKIFBAkvs-unsplash.jpg",
        "crop": (0.05, 0.02, 0.80, 0.95),
        "at": (0.44, 0.29), "height": 0.44, "finish": "wood",
        "light": (1.0, -0.6), "soft": 0.032, "lift": 0.88,
    },
    "ochre_sofa_b": {
        "file": "josh-sorenson-OxyKIFBAkvs-unsplash.jpg",
        "crop": (0.18, 0.00, 0.86, 0.86),
        "at": (0.38, 0.34), "height": 0.52, "finish": "black",
        "light": (1.0, -0.6), "soft": 0.030, "lift": 0.90,
    },
    "green_sofa_a": {
        "file": "katja-rooke-77JACslA8G0-unsplash.jpg",
        "crop": (0.00, 0.00, 0.60, 0.60),
        "at": (0.46, 0.44), "height": 0.58, "finish": "wood",
        "light": (0.8, -0.9), "soft": 0.040, "lift": 1.02,
    },
    "green_sofa_b": {
        "file": "katja-rooke-77JACslA8G0-unsplash.jpg",
        "crop": (0.02, 0.02, 0.56, 0.72),
        "at": (0.44, 0.38), "height": 0.60, "finish": "oak",
        "light": (0.8, -0.9), "soft": 0.042, "lift": 1.02,
    },
    # 灰のソファの上。白い壁で、光は左の窓から。
    "grey_sofa": {
        "file": "dix-sept-qY3pLOIpt4w-unsplash.jpg",
        "crop": (0.00, 0.14, 1.00, 0.74),
        "at": (0.50, 0.42), "height": 0.55, "finish": "wood",
        "light": (-0.8, -0.8), "soft": 0.038, "lift": 1.00,
    },
    # 濃い灰の壁とベンチ。暗い部屋にも掛かることを見せる1枚。
    "dark_bench": {
        "file": "evan-marvell-5LGaBQq3SzY-unsplash.jpg",
        "crop": (0.00, 0.04, 1.00, 0.62),
        "at": (0.50, 0.34), "height": 0.50, "finish": "oak",
        "light": (-0.5, -1.0), "soft": 0.036, "lift": 1.05,
    },
}

# 額の仕上げ。木の素材に掛ける色と明るさ。
FINISH = {
    "wood":  (1.00, 1.00, 1.00, 1.00),   # そのまま（濃い木）
    "oak":   (0.78, 1.02, 1.28, 1.55),   # 明るいオーク。青を落として赤を上げる
    "black": (1.00, 0.98, 0.96, 0.28),   # 黒。色味を消して暗く
}


def refinish(asset, name):
    """木枠の色を変える。額の造形はそのままに、色と明るさだけ動かす。"""
    b, g, r, lift = FINISH[name]
    out = asset.copy()
    px = out[:, :, :3].astype(np.float32)
    if name == "black":                       # 黒は彩度を落としてから暗くする
        gray = px.mean(axis=2, keepdims=True)
        px = gray * 0.75 + px * 0.25
    out[:, :, :3] = np.clip(px * np.array([b, g, r]) * lift, 0, 255).astype(np.uint8)
    return out


# ---------------------------------------------------------------- 額の素材

def descend(layers):
    for l in layers:
        yield l
        if l.is_group():
            yield from descend(l)


CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scene_src", "moulding.png")


def moulding():
    if os.path.exists(CACHE):
        a = cv2.imread(CACHE, cv2.IMREAD_UNCHANGED)
        bw, bh = [int(v) for v in open(CACHE + ".txt").read().split()]
        return a, bw, bh
    return _moulding_from_psd()


def _moulding_from_psd():
    """木枠の縁だけを、背景も影もなしで取り出す。

    PSD をそのまま平面化すると、乗算で重ねたグループが不透明に描かれて
    濃い塊になるので、必要なレイヤーだけを指定して描いている。
    """
    psd = PSDImage.open(os.path.join(PSD_DIR, "Wallderful horizontal freebie2.psd"))
    for l in descend(psd):
        l.visible = False
    for l in descend(psd):
        if l.name == "Frame texture # 1" and tuple(l.bbox) == (960, 531, 3243, 2374):
            l.visible = True
            node = l.parent
            while node is not None and node is not psd:
                node.visible = True
                node = node.parent
    a = np.array(psd.composite(force=True).convert("RGBA"))
    ys, xs = np.where(a[:, :, 3] > 8)
    a = a[ys.min():ys.max() + 1, xs.min():xs.max() + 1]

    # 縁の太さを測る。木枠は不透明で内側は抜けている。
    # 外周はぼかしで薄いので、中心から外へ歩いて木にぶつかった所を内側の縁とする。
    al = a[:, :, 3]
    hh, ww = al.shape
    row, col = al[hh // 2], al[:, ww // 2]
    if row[ww // 2] >= 128 or col[hh // 2] >= 128:
        raise SystemExit("額の内側が抜けていません")
    x = ww // 2
    while x > 0 and row[x] < 128:
        x -= 1
    y = hh // 2
    while y > 0 and col[y] < 128:
        y -= 1
    if x == 0 or y == 0:
        raise SystemExit("枠の内側の縁が見つかりません")
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    cv2.imwrite(CACHE, a)   # 並びはそのまま。読み書きで元に戻る
    open(CACHE + ".txt", "w").write(f"{x + 1} {y + 1}")
    return a, x + 1, y + 1


def nine_slice(asset, bw, bh, out_w, out_h):
    """角の造形を保ったまま、額を out_w x out_h に組み直す。

    ただ拡大すると木目と面取りが一緒に伸びて、太さが場所によって変わる。
    四隅はそのまま、辺だけを伸ばす。
    """
    h, w = asset.shape[:2]
    out = np.zeros((out_h, out_w, 4), asset.dtype)

    def put(dst_box, src_box, size):
        x0, y0 = dst_box
        sx0, sy0, sx1, sy1 = src_box
        piece = asset[sy0:sy1, sx0:sx1]
        if size != (piece.shape[1], piece.shape[0]):
            piece = cv2.resize(piece, size, interpolation=cv2.INTER_LINEAR)
        out[y0:y0 + piece.shape[0], x0:x0 + piece.shape[1]] = piece

    iw, ih = out_w - 2 * bw, out_h - 2 * bh          # 伸ばす辺の長さ
    put((0, 0),              (0, 0, bw, bh),           (bw, bh))
    put((out_w - bw, 0),     (w - bw, 0, w, bh),       (bw, bh))
    put((0, out_h - bh),     (0, h - bh, bw, h),       (bw, bh))
    put((out_w - bw, out_h - bh), (w - bw, h - bh, w, h), (bw, bh))
    put((bw, 0),             (bw, 0, w - bw, bh),      (iw, bh))
    put((bw, out_h - bh),    (bw, h - bh, w - bw, h),  (iw, bh))
    put((0, bh),             (0, bh, bw, h - bh),      (bw, ih))
    put((out_w - bw, bh),    (w - bw, bh, w, h - bh),  (bw, ih))
    # 内側は作品で覆われるので、額の中の色で埋めておく
    out[bh:out_h - bh, bw:out_w - bw] = asset[asset.shape[0] // 2, asset.shape[1] // 2]
    return out


# ---------------------------------------------------------------- 合成

def drop_shadow(alpha, light, soft, strength=0.55):
    """額の形から、光の反対側に落ちる影を作る。"""
    k = max(3, int(soft) | 1)
    sh = cv2.GaussianBlur(alpha.astype(np.float32) / 255.0, (k, k), 0)
    dx = int(-light[0] * soft * 0.55)
    dy = int(-light[1] * soft * 0.55)
    sh = np.roll(np.roll(sh, dy, axis=0), dx, axis=1)
    return np.clip(sh * strength, 0, 1)


def build(name, spec, asset, bw, bh, orient="tall"):
    photo = cv2.imread(os.path.join(PHOTO_DIR, spec["file"]))
    if photo is None:
        raise SystemExit("写真が読めません: " + spec["file"])
    H, W = photo.shape[:2]
    x0, y0, x1, y1 = [int(v * s) for v, s in
                      zip(spec["crop"], (W, H, W, H))]
    # 6種類すべて同じ縦横比で書き出す。TOPは4枚ずつの行で敷き詰めるので、
    # 比がばらつくと行の高さが揃わず、隙間や段差ができる。
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    cw, ch = x1 - x0, y1 - y0
    if cw / ch > OUT_ASPECT:
        cw = ch * OUT_ASPECT
    else:
        ch = cw / OUT_ASPECT
    x0, y0 = int(max(0, min(cx - cw / 2, W - cw))), int(max(0, min(cy - ch / 2, H - ch)))
    photo = photo[y0:y0 + int(ch), x0:x0 + int(cw)]
    out_h = int(round(OUT_W / OUT_ASPECT))
    photo = cv2.resize(photo, (OUT_W, out_h), interpolation=cv2.INTER_AREA)

    # 額の外側の大きさ。内側がちょうど 1:√2 になるよう縁の分を足す
    inner_h = int(out_h * spec["height"])
    inner_w = int(inner_h * RATIO) if orient == "tall" else int(inner_h / RATIO)
    scale = inner_h / (asset.shape[0] - 2 * bh)
    sbw, sbh = max(2, int(bw * scale)), max(2, int(bh * scale))
    fw, fh = inner_w + 2 * sbw, inner_h + 2 * sbh
    frame = nine_slice(asset, bw, bh, int(fw / scale), int(fh / scale))
    frame = cv2.resize(frame, (fw, fh), interpolation=cv2.INTER_AREA)

    cx, cy = int(spec["at"][0] * OUT_W), int(spec["at"][1] * out_h)
    x0, y0 = cx - fw // 2, cy - fh // 2

    # 置く場所の壁の明るさに額を寄せる。そのままだと浮く。
    pad = int(fh * 0.25)
    ys, xs = slice(max(0, y0 - pad), min(out_h, y0 + fh + pad)), \
             slice(max(0, x0 - pad), min(OUT_W, x0 + fw + pad))
    wall_mean = photo[ys, xs].reshape(-1, 3).mean(axis=0)
    tint = (wall_mean / max(1.0, wall_mean.mean())) * spec["lift"]

    canvas = photo.astype(np.float32)
    soft = fh * spec["soft"]

    # 影 → 額 の順に置く
    big = np.zeros((out_h, OUT_W), np.uint8)
    big[y0:y0 + fh, x0:x0 + fw] = frame[:, :, 3]
    sh = drop_shadow(big, spec["light"], soft)[..., None]
    canvas *= (1 - sh * 0.62)

    al = (frame[:, :, 3:4].astype(np.float32) / 255.0)
    fr = np.clip(frame[:, :, :3].astype(np.float32) * tint, 0, 255)
    roi = canvas[y0:y0 + fh, x0:x0 + fw]
    canvas[y0:y0 + fh, x0:x0 + fw] = fr * al + roi * (1 - al)

    img = np.clip(canvas, 0, 255).astype(np.uint8)
    quad = [[x0 + sbw, y0 + sbh], [x0 + fw - sbw, y0 + sbh],
            [x0 + fw - sbw, y0 + fh - sbh], [x0 + sbw, y0 + fh - sbh]]
    return img, quad, (OUT_W, out_h)


def main():
    asset, bw, bh = moulding()
    print(f"木枠 {asset.shape[1]}x{asset.shape[0]}  縁の太さ 横{bw} 縦{bh}")

    os.makedirs(OUT, exist_ok=True)
    man = os.path.join(OUT, "scenes.json")
    sc = json.load(open(man, encoding="utf-8")) if os.path.exists(man) else {}

    for name, spec in PHOTOS.items():
        tinted = refinish(asset, spec.get("finish", "wood"))
        for orient in ("tall", "wide"):
          for sz, mm in SIZES.items():
            s = dict(spec)
            s["height"] = spec["height"] * mm / SIZES[ANCHOR]
            if orient == "wide":                 # 横向きは短いほうが背になる
                s["height"] *= RATIO
            img, quad, size = build(name, s, tinted, bw, bh, orient)
            # 基準の判はいままでのファイル名のまま。増えるのは小さい判のぶんだけ
            key = f"{name}_{orient}" + ("" if sz == ANCHOR else f"_{sz}")
            cv2.imwrite(os.path.join(OUT, key + ".jpg"), img,
                        [cv2.IMWRITE_JPEG_QUALITY, 90])
            sc[key] = {"bg": key + ".jpg", "size": list(size), "quads": [quad],
                       "print": sz,
                       "src": spec["file"] + "（額は Wallderful の木枠を A/B判に組み直し）"}
            w = quad[1][0] - quad[0][0]
            h = quad[2][1] - quad[1][1]
            print(f"  {key:24} 内側 {w}x{h} 比 {min(w,h)/max(w,h):.3f}")

    json.dump(sc, open(man, "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
