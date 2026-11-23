#!/usr/bin/env python3
"""Render assets/demo.gif from REAL captured outputs (see assets/demo-outputs/*.txt).
Needs Pillow and ffmpeg. Frames are drawn text, the outputs are what the scripts printed."""
import os
import subprocess
import sys
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
W, H, FPS = 1000, 560, 10
FONT = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 15)
BG, FG, DIM, GREEN, RED = (15, 23, 42), (226, 232, 240), (125, 140, 165), (74, 222, 128), (248, 113, 113)
LH, PAD, MAXC = 21, 18, 108

SCENES = [
    ("python3 skills/ai-crawler-access/check_crawlers.py nytimes.com --no-probe", "o1.txt", 5.0),
    ("python3 skills/llms-txt/llms_txt.py validate stripe.com", "o2.txt", 3.2),
    ("python3 skills/citation-gap/gap.py probes/2026-11-23.jsonl --domain citedby.eu --min-share 1", "o3.txt", 5.0),
]


def color_for(line):
    l = line.lower()
    if "blocked" in l or l.startswith("error"):
        return RED
    if "allowed" in l or l.startswith("ok"):
        return GREEN
    if l.startswith(("info", "note", "not measured", "read this")):
        return DIM
    return FG


def frame(lines, cursor=True):
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    d.ellipse((16, 14, 28, 26), fill=(239, 68, 68)); d.ellipse((36, 14, 48, 26), fill=(234, 179, 8)); d.ellipse((56, 14, 68, 26), fill=(34, 197, 94))
    d.text((W // 2 - 120, 13), "ai-search-skills  -  real output", font=FONT, fill=DIM)
    y = 46
    for text, col in lines[-24:]:
        d.text((PAD, y), text, font=FONT, fill=col); y += LH
    return im


def main():
    out_dir = os.path.join(HERE, "demo-frames")
    os.makedirs(out_dir, exist_ok=True)
    n = 0

    def save(im, hold=1):
        nonlocal n
        for _ in range(hold):
            im.save(os.path.join(out_dir, "f%04d.png" % n)); n += 1

    for cmd, fn, hold in SCENES:
        out = [l[:MAXC - 1] + ("…" if len(l) > MAXC else "") for l in open(os.path.join(HERE, "demo-outputs", fn), encoding="utf-8").read().splitlines()]
        out = out[:22]
        prompt = "$ "
        for i in range(0, len(cmd) + 1, 3):
            save(frame([(prompt + cmd[:i] + "▌", GREEN)]))
        save(frame([(prompt + cmd, GREEN)]), 4)
        shown = [(prompt + cmd, GREEN)]
        for l in out:
            shown.append((l, color_for(l)))
            save(frame(shown), 1)
        save(frame(shown), int(hold * FPS))
    subprocess.check_call(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", os.path.join(out_dir, "f%04d.png"),
                           "-vf", "split[a][b];[a]palettegen=max_colors=48[p];[b][p]paletteuse=dither=none",
                           os.path.join(HERE, "demo.gif")])
    for f in os.listdir(out_dir):
        os.remove(os.path.join(out_dir, f))
    os.rmdir(out_dir)
    print("wrote", os.path.join(HERE, "demo.gif"), n, "frames")


if __name__ == "__main__":
    sys.exit(main())
