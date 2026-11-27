import os; BDIR = os.path.dirname(os.path.abspath(__file__))
import sys, json
from PIL import Image, ImageDraw, ImageFont
pre, kind, cols, out = sys.argv[1:5]
names = json.load(open(f'{BDIR}/people/{pre}_{kind}.json'))
ims = [Image.open(f'{BDIR}/people/{pre}_{kind}_{i:02d}.png').convert('RGB') for i in range(len(names))]
cols = int(cols); rows = (len(ims) + cols - 1) // cols; w, h = ims[0].size
S = Image.new('RGB', (w * cols, (h + 20) * rows), (30, 30, 36)); d = ImageDraw.Draw(S)
try: f = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 15)
except Exception: f = None
for i, (im, n) in enumerate(zip(ims, names)):
    x, y = (i % cols) * w, (i // cols) * (h + 20); S.paste(im, (x, y)); d.text((x + 8, y + h + 2), n, fill=(255, 200, 60), font=f)
S.save(out)
