#!/usr/bin/env python3
"""BASE の商品を index.html の各作品に紐付ける。

作品ファイル名 -> (商品ID, 商品名, 価格, シリーズ) の対応表。
サイトの40作品と BASE の40商品はちょうど1対1で対応している
（B4=inside1, A4=inside2, girls, Collage, small world, Beautiful Women）。

ファイル名の照合は NFC に正規化してから行う。リポジトリには
濁点が分解された形（NFD）で入っているファイルが2つあるため。
"""
import json
import os
import re
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOP = "https://artline.shopselect.net"

BASE = {
    "time_B4": ("139410644", "時間", 6000, "inside1"),
    "swing_B4": ("139410565", "ブランコ", 6000, "inside1"),
    "tears_B4": ("139410541", "涙", 6000, "inside1"),
    "polygon_B4": ("139410500", "ポリゴン", 6000, "inside1"),
    "honey_B4": ("139410456", "はちみつ", 6000, "inside1"),
    "hide-and-seek_B4": ("139410393", "かくれんぼ", 6000, "inside1"),
    "atami_B4": ("139410358", "熱海", 6000, "inside1"),
    "grape_B4": ("139410306", "ぶどうの味", 6000, "inside1"),
    "rabbitplanet _B4": ("139410244", "うさぎの惑星", 6000, "inside1"),
    "maze_B4": ("139410183", "迷路", 6000, "inside1"),
    "rainman_B4": ("139409986", "雨男", 6000, "inside1"),
    "Petrichor": ("139308969", "Petrichor", 18000, "Collage"),
    "Rank": ("139308954", "Rank", 18000, "Collage"),
    "Magic": ("139308940", "Magic", 18000, "Collage"),
    "未解決": ("139308905", "未解決", 18000, "Collage"),
    "time_A4": ("139308759", "Time", 7000, "inside2"),
    "spring_A4": ("139308751", "Spring", 7000, "inside2"),
    "honey_A4": ("139308727", "Honey", 7000, "inside2"),
    "grape_A4": ("139308714", "Grape", 7000, "inside2"),
    "swing_A4": ("139308700", "Swing", 7000, "inside2"),
    "tears_A4": ("139308685", "Tears", 7000, "inside2"),
    "moon_A4": ("139308675", "三日月", 7000, "inside2"),
    "rainman_A4": ("139308662", "雨男", 7000, "inside2"),
    "聞いていないようで聞いてるの図": ("139308265", "聞いていないようで聞いてるの図", 7000, "girls"),
    "背伸び": ("139308244", "背伸びも図", 7000, "girls"),
    "今忙しいの図": ("139308229", "今忙しいの図", 7000, "girls"),
    "睡魔の図": ("139305382", "睡魔の図", 7000, "girls"),
    "後ろいます": ("139308217", "後ろいますの図", 7000, "girls"),
    "あついなぁ": ("139308201", "あついなぁの図", 7000, "girls"),
    "Chopsticks": ("139308181", "Chopsticksの図", 7000, "girls"),
    "Rely": ("139307815", "Rely", 30000, "small world"),
    "Imitation girl": ("139307786", "Imitation girl", 30000, "small world"),
    "Beautiful memory": ("139307750", "Beautiful memory", 30000, "small world"),
    "ROOM 202": ("139307715", "ROOM 202", 30000, "small world"),
    "SOS": ("139304480", "SOS", 30000, "small world"),
    "women05_B2": ("139307412", "Compass", 35000, "Beautiful Women"),
    "women04_B2": ("139307299", "Earrings", 35000, "Beautiful Women"),
    "women03_B2": ("139306964", "Thread", 35000, "Beautiful Women"),
    "women02_B2": ("139299191", "GREENEYES", 35000, "Beautiful Women"),
    "women01_B1": ("139298895", "Seeds", 35000, "Beautiful Women"),
}
N = {unicodedata.normalize("NFC", k): v for k, v in BASE.items()}

# 「サイズ」欄に出す表記
SIZE = {"inside1": "B4 (257×364mm)", "inside2": "A4 (210×297mm)",
        "girls": "A4 (210×297mm)", "Collage": "額装作品",
        "small world": "原画 (一点物)", "Beautiful Women": "原画 (一点物)"}


def main():
    p = os.path.join(ROOT, "index.html")
    h = open(p, encoding="utf-8").read()
    files = re.findall(r'\{f:"([^"]+)"', h)
    miss = []
    for f in files:
        stem = unicodedata.normalize("NFC", f.rsplit(".", 1)[0])
        rec = N.get(stem)
        if not rec:
            miss.append(f)
            continue
        item, name, price, series = rec
        add = f',b:"{item}",p:{price},sz:"{SIZE[series]}",sr:"{series}"'
        old = '{f:"' + f + '"'
        i = h.index(old)
        j = h.index("}", i)
        if ",b:" not in h[i:j]:
            h = h[:j] + add + h[j:]
    if miss:
        raise SystemExit("未マッピング: " + ", ".join(miss))
    open(p, "w", encoding="utf-8").write(h)
    print(f"{len(files)} 作品に BASE 商品を紐付けました -> {SHOP}")


if __name__ == "__main__":
    main()
