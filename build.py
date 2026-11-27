# Builds dist/index.html: embeds the .glb models and menu art into src/index.html.
import base64, json, os
H = os.path.dirname(os.path.abspath(__file__))
A = lambda *p: os.path.join(H, *p)
src = open(A('src', 'index.html')).read()
data = {k: base64.b64encode(open(A('assets', 'cars', f'{k}.glb'), 'rb').read()).decode() for k in ['saloon', 'sports', 'van', 'police']}
for k in ['male', 'female']: data['human_' + k] = base64.b64encode(open(A('assets', 'people', f'{k}.glb'), 'rb').read()).decode()
assert '/*MODEL_DATA*/{}' in src and '/*ART_CSS*/' in src
out = src.replace('/*MODEL_DATA*/{}', json.dumps(data))
arts = ['chase', 'hero', 'street', 'dusk']
css = ''.join(".art.a%d{background-image:url(data:image/jpeg;base64,%s)}" % (i + 1, base64.b64encode(open(A('assets', 'art', f'{a}.jpg'), 'rb').read()).decode()) for i, a in enumerate(arts))
out = out.replace('/*ART_CSS*/', css)
os.makedirs(A('dist'), exist_ok=True)
open(A('dist', 'index.html'), 'w').write(out)
print('built', len(out) // 1024, 'KB')
