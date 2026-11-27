import os; BDIR = os.path.dirname(os.path.abspath(__file__))
import sys, os
from PIL import Image, ImageFilter, ImageOps, ImageEnhance, ImageDraw, ImageChops
CROPS={'street':(300,120,1220,637)}
def comic(src, dst, W=1152, H=648):
    im = Image.open(src).convert('RGB')
    n=os.path.splitext(os.path.basename(src))[0]
    if n in CROPS: im=im.crop(CROPS[n])
    im = im.resize((W, H), Image.LANCZOS)
    im = ImageEnhance.Color(im).enhance(1.2)
    im = ImageEnhance.Contrast(im).enhance(1.18)
    flat = im.filter(ImageFilter.MedianFilter(5)).quantize(colors=28, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).convert('RGB')
    # ink lines from luminance + colour edges
    g = im.convert('L').filter(ImageFilter.GaussianBlur(1))
    e1 = g.filter(ImageFilter.FIND_EDGES)
    e2 = flat.convert('L').filter(ImageFilter.FIND_EDGES)
    e = ImageChops.lighter(e1, e2).point(lambda v: 255 if v > 26 else 0).filter(ImageFilter.MaxFilter(3))
    ink = Image.new('RGB', (W, H), (18, 12, 10))
    out = Image.composite(ink, flat, e)
    # halftone dots in the shadows
    lum = out.convert('L')
    dots = Image.new('L', (W, H), 255); d = ImageDraw.Draw(dots); step = 7
    for y in range(0, H, step):
        for x in range((y // step % 2) * step // 2, W, step):
            v = lum.getpixel((min(x, W - 1), min(y, H - 1)))
            if v < 110:
                r = (110 - v) / 110 * step * .42
                d.ellipse([x - r, y - r, x + r, y + r], fill=150)
    out = ImageChops.multiply(out, Image.merge('RGB', (dots, dots, dots)))
    # warm print tint + vignette
    tint = Image.new('RGB', (W, H), (255, 246, 232))
    out = ImageChops.multiply(out, tint)
    vig = Image.new('L', (W, H), 0); vd = ImageDraw.Draw(vig)
    vd.ellipse([-W * .25, -H * .35, W * 1.25, H * 1.35], fill=255); vig = vig.filter(ImageFilter.GaussianBlur(120))
    out = Image.composite(out, ImageEnhance.Brightness(out).enhance(.45), vig)
    out.save(dst, 'JPEG', quality=70, optimize=True, progressive=True)
for f in sys.argv[1:]:
    n = os.path.splitext(os.path.basename(f))[0]
    comic(f, f'{BDIR}/art/comic/{n}.jpg')
    print(n, os.path.getsize(f'{BDIR}/art/comic/{n}.jpg') // 1024, 'KB')
