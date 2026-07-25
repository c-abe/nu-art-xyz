#!/usr/bin/env python3
"""モックアップ PSD を走査して、平面化画像と「差し込み枠」候補を書き出す。

PSD には作品を差し込むためのレイヤー（スマートオブジェクトや
"Your Design Here" などの名前）が入っていることが多い。
そのレイヤーの bbox がそのまま配置枠になるので、探して記録する。

1ファイルずつ処理して結果を /tmp/psdscan に貯めるので、
途中で止まっても再実行すれば続きから進む。
"""
import glob
import json
import os
import sys
import traceback
import warnings

warnings.filterwarnings("ignore")

from PIL import Image
from psd_tools import PSDImage

# モックアップ PSD の置き場。整理して ~/Desktop/AIの作業場/nu-art/素材/モックPSD に移した。
# Claude のサンドボックスからはマウント先が毎回変わるので、環境変数で上書きできるようにしてある。
#   MOCK_PSD_DIR=/path/to/モックPSD python3 tools/psd_extract.py
SRC = os.environ.get(
    "MOCK_PSD_DIR",
    os.path.expanduser("~/Desktop/AIの作業場/nu-art/素材/モックPSD"),
)
OUT = "/tmp/psdscan"
PREVIEW_W = 900

# 差し込み枠らしいレイヤー名。小文字で部分一致を見る。
HINTS = [
    "your design", "your poster", "poster design", "your artwork", "your image",
    "design here", "place your", "paste", "artwork", "graphic", "poster",
    "デザイン", "ここに", "差し替え",
]
# 背景・影・効果など、枠ではないもの
DENY = ["background", "bg", "shadow", "light", "effect", "vignette", "template",
        "mask", "multiply", "overlay", "freepik", "logo", "バナー"]


def score(name):
    n = name.lower()
    if any(d in n for d in DENY) and not any(h in n for h in HINTS[:6]):
        return -1
    return sum(2 for h in HINTS if h in n)


def flatten(layers, depth=0, path=""):
    for l in layers:
        p = f"{path}/{l.name}"
        yield l, p, depth
        if l.is_group() and depth < 3:
            yield from flatten(l, depth + 1, p)


def process(path):
    name = os.path.splitext(os.path.basename(path))[0]
    stem = name.replace(" ", "_")
    meta_path = os.path.join(OUT, stem + ".json")
    if os.path.exists(meta_path):
        return "skip"

    psd = PSDImage.open(path)
    W, H = psd.width, psd.height

    cands = []
    for l, p, _ in flatten(psd):
        b = l.bbox
        if not b:
            continue
        w, h = b[2] - b[0], b[3] - b[1]
        if w < W * 0.05 or h < H * 0.05:
            continue
        if w * h > W * H * 0.92:          # 背景まるごとは枠ではない
            continue
        s = score(l.name)
        if l.kind == "smartobject":
            s += 3
        if s <= 0:
            continue
        cands.append({"name": l.name, "path": p, "kind": str(l.kind),
                      "bbox": [int(v) for v in b], "score": s,
                      "visible": bool(l.visible)})
    cands.sort(key=lambda c: (-c["score"], -(c["bbox"][2] - c["bbox"][0])))

    img = psd.composite()
    if img is None:
        raise RuntimeError("composite が None")
    img = img.convert("RGB")
    if img.width > PREVIEW_W:
        img = img.resize((PREVIEW_W, round(img.height * PREVIEW_W / img.width)),
                         Image.LANCZOS)
    img.save(os.path.join(OUT, stem + ".jpg"), quality=82)

    meta = {"file": os.path.relpath(path, SRC), "size": [W, H],
            "candidates": cands[:6]}
    json.dump(meta, open(meta_path, "w"), ensure_ascii=False, indent=1)
    return "ok"


def main():
    os.makedirs(OUT, exist_ok=True)
    files = sorted(glob.glob(os.path.join(SRC, "**", "*.psd"), recursive=True),
                   key=os.path.getsize)          # 軽いものから
    budget = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    done = 0
    for f in files:
        if done >= budget:
            break
        try:
            r = process(f)
        except Exception as e:
            stem = os.path.splitext(os.path.basename(f))[0].replace(" ", "_")
            json.dump({"file": f, "error": f"{type(e).__name__}: {e}"},
                      open(os.path.join(OUT, stem + ".json"), "w"), ensure_ascii=False)
            print(f"  NG {os.path.basename(f)}: {type(e).__name__}: {e}")
            traceback.print_exc(limit=1)
            done += 1
            continue
        if r == "ok":
            done += 1
            m = json.load(open(os.path.join(OUT,
                os.path.splitext(os.path.basename(f))[0].replace(" ", "_") + ".json")))
            top = m["candidates"][0] if m["candidates"] else None
            print(f"  OK {os.path.basename(f)}  {m['size'][0]}x{m['size'][1]}  "
                  f"枠候補={top['name'] if top else 'なし'} {top['bbox'] if top else ''}")

    total = len(files)
    fin = len(glob.glob(os.path.join(OUT, "*.json")))
    print(f"進捗 {fin}/{total}")


if __name__ == "__main__":
    main()
