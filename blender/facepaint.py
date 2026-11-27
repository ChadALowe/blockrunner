"""Stylised cartoon face painted onto the head's sphere texture (u=.25 is the front, v=.5 the eye line).
Mirrors the runtime canvas painter in the game."""
import os; BDIR = os.path.dirname(os.path.abspath(__file__))
from PIL import Image, ImageDraw, ImageFilter

W, H = 512, 256
CX = 128

def mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))

def hexrgb(h):
    return ((h >> 16) & 255, (h >> 8) & 255, h & 255)

def paint(skin=0xc99a78, hair=0x2a1a10, eye=0x4a2e1a, female=False, path='/tmp/face.png', hairline=True, stubble=False):
    sk = hexrgb(skin); hr = hexrgb(hair); ey = hexrgb(eye)
    S = 2  # supersample
    im = Image.new('RGB', (W * S, H * S), sk); d = ImageDraw.Draw(im)
    def E(cx, cy, rx, ry, col): d.ellipse([(cx - rx) * S, (cy - ry) * S, (cx + rx) * S, (cy + ry) * S], fill=col)
    if hairline:
        P = [(0, 0), (512, 0), (512, 66), (270, 72), (192, 92), (186, 118), (176, 90), (156, 80), (128, 78), (100, 80), (80, 90), (70, 118), (64, 92), (-14, 72), (0, 66)]
        d.polygon([(x * S, y * S) for x, y in P], fill=mix(hr, sk, .08))
    if stubble:   # soft painted shadow over the jaw, cheeks and upper lip
        st = Image.new('L', (W * S, H * S), 0); ds = ImageDraw.Draw(st)
        ds.polygon([(x * S, y * S) for x, y in [(52, 128), (70, 146), (98, 148), (112, 150), (128, 149), (144, 150), (158, 148), (186, 146), (204, 128),
                                               (206, 170), (186, 196), (160, 212), (128, 218), (96, 212), (70, 196), (50, 170)]], fill=225 if stubble == 'heavy' else 175)
        ds.ellipse([(CX - 15) * S, (153) * S, (CX + 15) * S, (166) * S], fill=0)
        st = st.filter(ImageFilter.GaussianBlur(3 * S))
        im = Image.composite(Image.new('RGB', im.size, mix(sk, hr, .62 if stubble == 'heavy' else .48)), im, st); d = ImageDraw.Draw(im)
        import random as _r; _r.seed(7); dc = mix(sk, hr, .8)
        for _ in range(1500 if stubble == 'heavy' else 900):   # stubble speckle
            x_, y_ = _r.uniform(54, 202), _r.uniform(140, 216)
            if st.getpixel((int(x_ * S), int(y_ * S))) > 110: d.ellipse([x_ * S - 1.6, y_ * S - 1.6, x_ * S + 1.6, y_ * S + 1.6], fill=dc)
    # blush
    bl = Image.new('RGBA', im.size, (0, 0, 0, 0)); db = ImageDraw.Draw(bl)
    for cx in (CX - 44, CX + 44):
        db.ellipse([(cx - 15) * S, (138 - 9) * S, (cx + 15) * S, (138 + 9) * S], fill=(235, 110, 110, 70 if female else 34))
    bl = bl.filter(ImageFilter.GaussianBlur(5 * S))
    im = Image.alpha_composite(im.convert('RGBA'), bl); d = ImageDraw.Draw(im)
    outline = mix(sk, (25, 12, 10), .8)
    for i, ex in enumerate((CX - 30, CX + 30)):
        E(ex, 117, 13.5, 16.5, outline)                 # outline
        E(ex, 117, 12, 15, (252, 250, 246))              # white
        E(ex + (1 if i else -1), 120, 8, 10, ey)          # iris
        E(ex + (1 if i else -1), 121, 4.6, 5.8, (14, 12, 14))  # pupil
        E(ex + (4 if i else 2), 114.5, 2.8, 2.8, (255, 255, 255))  # highlight
        E(ex - (2 if i else 4) + 2, 124, 1.4, 1.4, (255, 255, 255))
        lw = 4 if female else 3
        d.arc([(ex - 14) * S, (100) * S, (ex + 14) * S, (132) * S], 200, 340, fill=outline, width=lw * S)   # upper lid
        if female:
            sx = 1 if i else -1
            d.line([((ex + sx * 12) * S, 106 * S), ((ex + sx * 17) * S, 101 * S)], fill=outline, width=3 * S)
        bc = mix(hr, (0, 0, 0), .2)
        d.line([((ex - 12) * S, (92 + (2 if i == 0 else 0)) * S), (ex * S, 88 * S), ((ex + 12) * S, (92 + (0 if i == 0 else 2)) * S)],
               fill=bc, width=(5 if female else 8) * S, joint='curve')
    # smile
    mc = mix(sk, (110, 30, 30), .7) if not female else mix(sk, (190, 50, 80), .7)
    d.arc([(CX - 15) * S, (150) * S, (CX + 15) * S, (168) * S], 20, 160, fill=mc, width=4 * S)
    im = im.convert('RGB').resize((W, H), Image.LANCZOS)
    im.save(path)
    return path

if __name__ == '__main__':
    paint(path=f'{BDIR}/people/face_test.png')
