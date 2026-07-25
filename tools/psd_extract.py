#!/usr/bin/env python3
"""モックアップ PSD から「作品を抜いた背景」と「額の四隅」を取り出す。

PSD には作品を差し込むレイヤー（スマートオブジェクト）が入っている。
そのレイヤーだけを描画して不透明部分の輪郭を取れば、傾いた額でも
四隅がそのまま得られる。作品レイヤーと透かしを消して描画すれば背景になる。

1ファイル＝1シーンとは限らない。women_mock01.psd のように
mockup1 / mockup12 / ... と複数シーンが重ねてあるものは、
グループごとに1シーンとして切り出す。

    python3 tools/psd_extract.py <PSDのパス> [処理する上限]

出力先 tools/scene_src/ :
    <scene>.jpg   作品を抜いた背景
    <scene>.json  額の四隅とサイズ
"""
import glob
import json
import os
import sys
import warnings

warnings.filterwarnings("ignore")

import cv2
import numpy as np
from PIL import Image
from psd_tools import PSDImage
from psd_tools.constants import Tag

# モックアップ PSD の置き場。整理して ~/Desktop/AIの作業場/nu-art/素材/モックPSD に移した。
# Claude のサンドボックスからはマウント先が毎回変わるので、環境変数で上書きできるようにしてある。
#   MOCK_PSD_DIR=/path/to/モックPSD python3 tools/psd_extract.py
SRC = os.environ.get(
    "MOCK_PSD_DIR",
    os.path.expanduser("~/Desktop/AIの作業場/nu-art/素材/モックPSD"),
)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scene_src")

# 作品が入るレイヤーの名前（小文字で部分一致）
PLACE = ("mockup", "your poster", "poster design", "design here", "your design",
         "your image", "graphic", "place your", "project_here", "poster (edit",
         "artwork", "poster")
# 背景・効果など、作品枠ではないもの
NOT_PLACE = ("background", "bg", "shadow", "vignette", "template multiply",
             "mask", "reflect", "light", "effect", "multiply", "stuff")
# 透かしバッジ（本人のものなので非表示にしてよいと確認済み）
WATERMARK = ("ベクトルスマートオブジェクト", "freepik", "original", "digital download")


def is_place(name):
    n = name.lower()
    if any(k in n for k in NOT_PLACE):
        return False
    return any(k in n for k in PLACE)


def is_watermark(name):
    n = name.lower()
    return any(k in n for k in WATERMARK)


def _overlap(a, b):
    """2つの bbox の重なりを、小さい方の面積に対する割合で返す。"""
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    inter = (x1 - x0) * (y1 - y0)
    small = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
    return inter / small if small else 0.0


def descend(layers):
    for l in layers:
        yield l
        if l.is_group():
            yield from descend(l)


def quad_of(psd, layer):
    """額の四隅を返す。

    スマートオブジェクトは配置時の変形行列を Trnf として持っている。
    傾いた額や奥行きのある額でもここに四隅がそのまま入っているので、
    画像から輪郭を推定するより正確で速い。
    無い場合だけ bbox を矩形として使う。
    """
    tb = getattr(layer, "tagged_blocks", None)
    if tb:
        for key in (Tag.SMART_OBJECT_LAYER_DATA1, Tag.SMART_OBJECT_LAYER_DATA2,
                    Tag.PLACED_LAYER1, Tag.PLACED_LAYER2):
            if key not in tb:
                continue
            data = getattr(tb.get_data(key), "data", None)
            if data is None:
                continue
            for field in (b"nonAffineTransform", b"Trnf"):
                try:
                    v = [float(x) for x in data[field]]
                except Exception:
                    continue
                if len(v) == 8 and (max(v[::2]) - min(v[::2])) > 2:
                    return [[round(v[i]), round(v[i + 1])] for i in (0, 2, 4, 6)]
    b = layer.bbox
    if not b:
        return None
    return [[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]]]


def render_bg(psd, scene, places):
    """シーンだけを表示し、作品レイヤーと透かしを消して描画する。"""
    saved = {id(l): l.visible for l in descend(psd)}
    try:
        for l in descend(psd):
            l.visible = False
        target = scene if scene is not None else psd
        if scene is not None:
            node = scene
            while node is not None and node is not psd:
                node.visible = True
                node = node.parent
            for l in descend(scene):
                l.visible = saved[id(l)]
        else:
            for l in descend(psd):
                l.visible = saved[id(l)]
        for l in descend(psd):
            if is_watermark(l.name) or any(l is p for p in places):
                l.visible = False
        img = psd.composite(force=True)
    finally:
        for l in descend(psd):
            l.visible = saved[id(l)]
    return img.convert("RGB") if img is not None else None


def process(path, budget):
    psd = PSDImage.open(path)
    stem = os.path.splitext(os.path.basename(path))[0].replace(" ", "_")

    # 上位グループが複数シーンを兼ねているか判定する
    tops = [l for l in psd if l.is_group()]
    multi = sum(1 for g in tops if any(is_place(x.name) for x in descend(g))) > 1
    scenes = [(g.name, g) for g in tops] if multi else [(None, None)]

    made = 0
    for sname, scene in scenes:
        if made >= budget:
            break
        pool = list(descend(scene)) if scene is not None else list(descend(psd))
        places = [l for l in pool if is_place(l.name) and l.bbox
                  and (l.bbox[2] - l.bbox[0]) > psd.width * 0.07
                  and (l.bbox[2] - l.bbox[0]) * (l.bbox[3] - l.bbox[1]) < psd.width * psd.height * 0.9]
        if not places:
            continue
        # 同じ額をグループと中身の両方で拾ってしまうので、
        # 実体のあるレイヤーを優先し、重なるものは1つに畳む
        places.sort(key=lambda l: (l.is_group(),
                                   -((l.bbox[2] - l.bbox[0]) * (l.bbox[3] - l.bbox[1]))))
        picked = []
        for l in places:
            if any(_overlap(l.bbox, q.bbox) > 0.5 for q in picked):
                continue
            picked.append(l)
        places = picked[:2]                      # 額は最大2枚まで

        name = stem + ("__" + sname.replace(" ", "_") if sname else "")
        if os.path.exists(os.path.join(OUT, name + ".json")):
            continue

        quads = []
        for p in places:
            q = quad_of(psd, p)
            if q:
                quads.append(q)
        if not quads:
            continue

        bg = render_bg(psd, scene, places)
        if bg is None:
            continue
        bg.save(os.path.join(OUT, name + ".jpg"), quality=90)
        json.dump({"src": os.path.relpath(path, SRC), "scene": sname,
                   "size": [psd.width, psd.height], "quads": quads},
                  open(os.path.join(OUT, name + ".json"), "w"),
                  ensure_ascii=False, indent=1)
        print(f"  OK {name}  {psd.width}x{psd.height}  額{len(quads)}枚")
        made += 1
    return made


def main():
    os.makedirs(OUT, exist_ok=True)
    target = sys.argv[1] if len(sys.argv) > 1 else None
    budget = int(sys.argv[2]) if len(sys.argv) > 2 else 99
    files = [target] if target else sorted(
        glob.glob(os.path.join(SRC, "**", "*.psd"), recursive=True), key=os.path.getsize)
    for f in files:
        try:
            process(f, budget)
        except Exception as e:
            print(f"  NG {os.path.basename(f)}: {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
