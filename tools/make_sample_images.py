"""生成示例用的微信风格截图（虚构人物、虚构案情，不含任何真实案件信息）。

用法：
    python tools/make_sample_images.py --out examples/sample_images

生成 3 张截图，模拟一起借款纠纷的微信对话，用于演示本工具的完整流程。
之所以使用合成数据而非真实截图：一是避免泄露当事人信息，
二是保证 README 中的示例可被任何人复现。
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import List, Tuple

from PIL import Image, ImageDraw, ImageFont

W, H = 720, 1280
BG = (237, 237, 237)
HEADER_BG = (237, 237, 237)
TITLE_COLOR = (25, 25, 25)
DATE_COLOR = (153, 153, 153)
TEXT_COLOR = (0, 0, 0)
ME_BUBBLE = (149, 236, 105)
YOU_BUBBLE = (255, 255, 255)
AVATAR_ME = (76, 175, 80)
AVATAR_YOU = (33, 150, 243)

FONT_CANDIDATES = [
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/msyhbd.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def load_font(size: int) -> ImageFont.FreeTypeFont:
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default()


Item = Tuple[str, str]  # (kind, text)  kind: date | me | you | sys


def wrap(draw, text: str, font, max_width: int) -> List[str]:
    lines, cur = [], ""
    for ch in text:
        if draw.textlength(cur + ch, font=font) <= max_width:
            cur += ch
        else:
            lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    return lines


def draw_chat(path: Path, title: str, items: List[Item]) -> None:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    f_title = load_font(32)
    f_date = load_font(22)
    f_text = load_font(28)

    # 顶部栏
    d.rectangle([0, 0, W, 96], fill=HEADER_BG)
    d.text((W // 2, 48), title, font=f_title, fill=TITLE_COLOR, anchor="mm")
    d.text((28, 48), "<", font=f_title, fill=TITLE_COLOR, anchor="lm")

    y = 130
    avatar, pad = 44, 18
    max_text_w = 430

    for kind, text in items:
        if kind == "date":
            d.text((W // 2, y), text, font=f_date, fill=DATE_COLOR, anchor="ma")
            y += 44
            continue
        if kind == "sys":
            d.text((W // 2, y), text, font=f_date, fill=DATE_COLOR, anchor="ma")
            y += 40
            continue

        lines = wrap(d, text, f_text, max_text_w)
        line_h = 38
        bubble_w = int(max(d.textlength(l, font=f_text) for l in lines)) + pad * 2
        bubble_h = len(lines) * line_h + pad * 2 - 6

        if kind == "me":
            x1 = W - 24 - avatar - 12
            x0 = x1 - bubble_w
            d.rounded_rectangle([x0, y, x1, y + bubble_h], radius=10, fill=ME_BUBBLE)
            d.rounded_rectangle(
                [W - 24 - avatar, y + 4, W - 24, y + 4 + avatar], radius=6, fill=AVATAR_ME
            )
        else:
            x0 = 24 + avatar + 12
            x1 = x0 + bubble_w
            d.rounded_rectangle([x0, y, x1, y + bubble_h], radius=10, fill=YOU_BUBBLE)
            d.rounded_rectangle([24, y + 4, 24 + avatar, y + 4 + avatar], radius=6, fill=AVATAR_YOU)

        for i, line in enumerate(lines):
            d.text((x0 + pad, y + pad + i * line_h), line, font=f_text, fill=TEXT_COLOR, anchor="la")

        y += bubble_h + 34
        if y > H - 60:
            break

    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, quality=92)


SAMPLE: List[List[Item]] = [
    [
        ("date", "2025年3月10日"),
        ("you", "李哥，最近资金周转不开，能不能借我5万应急？"),
        ("me", "可以，但要写个借条，三个月还。"),
        ("you", "没问题，我给你打借条，利息按银行同期利率算。"),
        ("me", "那我现在转你。"),
        ("me", "已转账50000元，你查收一下。"),
        ("you", "收到了，谢谢李哥！"),
    ],
    [
        ("date", "2025年6月12日"),
        ("me", "小王，三个月到了，那5万该还了吧？"),
        ("you", "李哥再宽限一个月，我这边回款就到了。"),
        ("me", "最迟下个月15号，不能再拖了。"),
        ("you", "好的，一定还。"),
        ("date", "2025年8月20日"),
        ("me", "又两个月了，钱到底什么时候还？"),
        ("you", "最近真的困难，能不能先还2万，剩下的年底结清？"),
        ("me", "不行，你必须按约定还。"),
        ("you", "那我没办法，你爱起诉就起诉吧。"),
    ],
    [
        ("date", "2025年9月5日"),
        ("me", "我最后问一次，还还是不还？"),
        ("you", "借条是我写的，钱我认，但现在真没钱。"),
        ("me", "那你把借条拍照发我。"),
        ("sys", "对方撤回了一条消息"),
        ("you", "我这边再想想办法。"),
        ("me", "尽快，我没有时间了。"),
    ],
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="examples/sample_images")
    args = ap.parse_args()
    outdir = Path(args.out)
    for i, items in enumerate(SAMPLE, 1):
        p = outdir / f"{i}.jpg"
        draw_chat(p, "王强", items)
        print(f"已生成 {p}")
    print(f"共 {len(SAMPLE)} 张示例截图 -> {outdir}")


if __name__ == "__main__":
    main()
