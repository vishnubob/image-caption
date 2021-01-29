#!/usr/bin/env python
#
# Command line script to add a caption to an image.
# Requires pillow.
#
# Author: Giles Hall <giles@polymerase.org>, (C) 2021

import os
import io
import sys
import argparse
from pathlib import Path
from zipfile import ZipFile
import urllib.error
from urllib.request import urlopen

def die(msg):
    print(f"Error: {msg}")
    sys.exit(1)

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    die("Pillow required, install with:\n $ pip install pillow")

class ImageTextWrapper(object):
    class Overflow(Exception):
        pass

    def textwrap(self, text, ff_overflow):
        (is_hovf, is_vovf) = ff_overflow
        wrapped = []
        line = []
        text = text.split(' ')
        for word in text:
            head = str.join('\n', wrapped)
            test_str = head + '\n' + str.join(' ', line + [word])
            if is_vovf(test_str):
                raise self.Overflow
            if is_hovf(test_str):
                wrapped.append(str.join(' ', line))
                line = [word]
            else:
                line.append(word)
        if line:
            wrapped.append(str.join(' ', line))
        text = str.join('\n', wrapped)
        if is_vovf(text):
            raise self.Overflow
        return text

    def size_and_wrap(self, text, bbox, font):
        text = str.join(' ', map(str.strip, text.strip().split('\n')))
        mat = Image.new("RGB", (bbox[2], bbox[3]))
        img_d = ImageDraw.Draw(mat)
        while font.size > 2:
            is_hovf = lambda tx: img_d.multiline_textbbox((0,0), tx, font=font)[-2] > mat.size[0]
            is_vovf = lambda tx: img_d.multiline_textbbox((0,0), tx, font=font)[-1] > mat.size[1]
            ff_ovf = (is_hovf, is_vovf)
            try:
                result = self.textwrap(text, ff_ovf)
                return (result, font)
            except self.Overflow:
                font_bytes = io.BytesIO(font.font_bytes)
                font = ImageFont.truetype(font_bytes, font.size - 1)
                continue
        raise self.Overflow

class ImageCaption(object):
    def __init__(self, height=None, margin=(2, 2, 2, 2), colors=('white', 'black'), font=None):
        self.margin = margin
        self.font = font
        self.colors = colors
        self.height = height 
        
    def get_margins(self, img, height):
        margins = (
            # left
            self.margin[0], 
            # top
            img.size[1] + self.margin[1], 
            # right
            img.size[0] - self.margin[2], 
            # bottom
            img.size[1] + height - self.margin[3]
        )
        return margins

    def get_textbox(self, img, height):
        bbox = (
            0, 0, 
            img.size[0] - (self.margin[0] + self.margin[2]),
            height - (self.margin[1] + self.margin[3])
        )
        return bbox

    def add_caption(self, img=None, text=None):
        height = int(round(img.size[1] * .15))  if self.height is None else self.height
        margins = self.get_margins(img, height)
        wrap = ImageTextWrapper()
        bbox = self.get_textbox(img, height)
        (text, font) = wrap.size_and_wrap(text, bbox, self.font)
        mat = Image.new("RGB", (img.size[0], img.size[1] + height), self.colors[1])
        img_d = ImageDraw.Draw(mat)
        img_d.multiline_text((margins[0], margins[1]), text, self.colors[0], font=font)
        mat.paste(img, (0, 0))
        return mat

class FontFactory(object):
    def __init__(self, font_family='roboto', font_style='regular', font_dir='.'):
        self.font_family = font_family
        self.font_style = font_style
        self.font_dir = Path(font_dir)

    @property
    def family_name(self):
        family = self.font_family.replace('_', ' ').replace('-', ' ')
        family = str.join(' ', map(str.capitalize, family.split(' ')))
        return family

    @property
    def archive_path(self):
        return os.path.join(self.font_dir, f"{self.family_name}.zip")

    def download(self):
        self.font_dir.mkdir(exist_ok=True)
        url = f"https://fonts.google.com/download?family={self.family_name}"

        try:
            resp = urlopen(url)
            with open(self.archive_path, 'wb') as fh:
                fh.write(resp.read())
        except urllib.error.HTTPError:
            return False
        return True

    def load(self, size=None):
        if not os.path.exists(self.archive_path):
            ok = self.download()
            if not ok:
                die("Font family not found")

        style_key = self.font_style.lower()
        keyf = lambda nm: nm.split('-')[-1].split('.')[0].lower()
        with ZipFile(self.archive_path) as zfh:
            names = {keyf(fn): fn for fn in zfh.namelist() if "license" not in fn.lower()}
            if style_key not in names:
                tbl = str.join(', ', names)
                msg = f"style '{self.font_style}' not available. Select one of:\n  {tbl}" 
                die(msg)
            font = io.BytesIO(zfh.read(names[style_key]))
            font = ImageFont.truetype(font, size)
            return font

def cli():
    default_font_dir = str(Path.home().joinpath('.config').joinpath('font-cache'))
    pr = argparse.ArgumentParser(description='Add caption to image')
    pr.add_argument('input_img', nargs=1, help='Image to caption')
    pr.add_argument('-c', '--caption', help='Specify caption text with this option or stdin')
    pr.add_argument('-m', '--margin', default='2', help='margin as integer or four integers, seperated by commas.')
    pr.add_argument('-f', '--font-family', default='roboto', help='Name of font family')
    pr.add_argument('-s', '--font-size', type=int, default=12, help='Max font size in pts')
    pr.add_argument('-S', '--font-style', default='regular', help='Font style (bold, italic, etc)')
    pr.add_argument('-D', '--font-dir', default=default_font_dir, help='Font directory (defaults to current directory)')
    pr.add_argument('-F', '--font-file', help='Path to font file')
    pr.add_argument('-H', '--height', type=int, default=30, help='Height of textbox')
    pr.add_argument('-C', '--colors', default='white,black', help='Foreground and background colors seperated by commas')
    pr.add_argument('-o', '--out', help='Path to save the output image')
    pr.add_argument('-i', '--input', help='Path to input image for captioning')
    return pr.parse_args()

def caption_image(img_path, caption, **kw):
    img = Image.open(img_path)
    icap = ImageCaption(**kw)
    return icap.add_caption(img, caption)

def main():
    args = cli()
    # caption
    if args.caption is None:
        args.caption = sys.stdin.read()
    # caption
    if args.colors and ',' in args.colors:
        args.colors = tuple(args.colors.split(','))
    # margin
    if args.margin:
        if ',' in args.margin:
            args.margin = list(map(int, args.margin.split(',')))
            assert len(args.margin) == 4, "margin requires one or four integers"
        else:
            args.margin = int(args.margin)
    # image paths
    in_img_path = Path(args.input_img[0])
    out_img_path = args.out or f"{in_img_path.stem}_caption{in_img_path.suffix}"
    if args.font_file:
        font = ImageFont.truetype(args.font_file, args.font_size)
    else:
        ff = FontFactory(args.font_family, args.font_style, args.font_dir)
        font = ff.load(args.font_size)
    out_img = caption_image(
        in_img_path, 
        args.caption, 
        height=args.height,
        margin=args.margin,
        colors=args.colors,
        font=font
    )
    out_img.save(out_img_path)

if __name__ == "__main__":
    main()
