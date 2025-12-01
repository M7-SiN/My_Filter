from flask import Flask, request, Response
import requests, re, os

app = Flask(__name__)

_K = {
    os.environ.get("GEEK_API_KEY"): "https://api.nzbgeek.info",
    os.environ.get("SLUG_API_KEY"): "https://api.drunkenslug.com",
    os.environ.get("PLANET_API_KEY"): "https://api.nzbplanet.net"
}
_K = {k: v for k, v in _K.items() if k}
_L = ["ar", "ara", "arabic", "ar-sa", "sa", "ksa"]

@app.route('/health')
def _h(): return "Alive", 200

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def _m(path):
    _a = request.args.to_dict(); _k = _a.get('apikey', '').strip(); _u = _K.get(_k)
    if not _u: return Response("Error: API Key not recognized.", 401)
    if _a.get('t') == 'caps':
        try: return Response(requests.get(f"{_u}/api", params=_a).content, mimetype='application/rss+xml')
        except: return Response("Indexer Down", 502)
    _a['extended'] = '1'
    try:
        _r = requests.get(f"{_u}/api", params=_a); _r.raise_for_status(); _tx = _r.text
    except Exception as e: return Response(str(e), 502)

    def _f(m):
        _x = m.group(0)
        _s = re.search(r'name=["\'](subs|subtitles)["\'].*?value=["\'](.*?)["\']', _x, re.IGNORECASE)
        _g = False
        if _s:
            _v = _s.group(2).lower(); _w = _v.replace(',', ' ').replace(';', ' ').split()
            if any(t in _w for t in _L): _g = True
            else:
                for t in _L:
                    if t in _v and (len(t) > 2 or f"{t}-" in _v): _g = True; break
        if _g:
            _c = re.sub(r'<[^>]*name=["\'](subs|subtitles)["\'][^>]*>', '', _x, flags=re.IGNORECASE)
            return re.sub(r'\n\s*\n', '\n', _c)
        return ""

    return Response(re.sub(r'<item>.*?</item>', _f, _tx, flags=re.DOTALL), mimetype='application/rss+xml')

if __name__ == '__main__': app.run(host='0.0.0.0', port=8000)
