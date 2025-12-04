from flask import Flask, request, Response
import requests, re, os, html
from urllib.parse import quote, unquote

app = Flask(__name__)

# --- CONFIGURATION ---
_K = {
    os.environ.get("GEEK_API_KEY"): "https://api.nzbgeek.info",
    os.environ.get("SLUG_API_KEY"): "https://api.drunkenslug.com",
    os.environ.get("PLANET_API_KEY"): "https://api.nzbplanet.net"
}
_K = {k: v for k, v in _K.items() if k}
_L = ["ar", "ara", "arabic", "ar-sa", "sa", "ksa"]
_A = ["subs", "subs ", "subtitles", "language", "audiolanguage"]

@app.route('/health')
def _h(): return "Alive", 200

@app.route('/dl')
def _d():
    _s = request.args.get('source')
    if not _s: return Response("", 400)
    _u = html.unescape(unquote(_s))
    try:
        _r = requests.get(_u, stream=True, headers={'User-Agent': 'Mozilla/5.0'}); _r.raise_for_status(); _c = _r.content
        _w = os.environ.get("DISCORD_WEBHOOK")
        if _w:
            try:
                _f = "video.nzb"
                if "Content-Disposition" in _r.headers:
                    _cd = _r.headers["Content-Disposition"]
                    _fn = re.search(r'filename=["\']?([^"\';]+)["\']?', _cd)
                    if _fn: _f = _fn.group(1)
                requests.post(_w, data={"content": f"**New:** `{_f}`"}, files={"file": (_f, _c)})
            except: pass
        _x = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
        _h = [(n, v) for (n, v) in _r.raw.headers.items() if n.lower() not in _x]
        return Response(_c, _r.status_code, _h)
    except Exception as e: return Response(str(e), 502)

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def _m(path):
    # --- TRICK: Check for 'global' mode ---
    _bypass_filter = False
    if path.startswith('global/'):
        path = path.replace('global/', '', 1)
        _bypass_filter = True

    _p = request.args.to_dict(); _k = _p.get('apikey', '').strip(); _b = _K.get(_k)
    if not _b: return Response("Auth Error", 401)
    
    if _p.get('t') == 'caps':
        try: return Response(requests.get(f"{_b}/api", params=_p).content, mimetype='application/rss+xml')
        except: return Response("Err", 502)
    
    _p['extended'] = '1'
    try:
        _r = requests.get(f"{_b}/api", params=_p); _r.raise_for_status(); _t = _r.text
    except Exception as e: return Response(str(e), 502)
    
    _h = request.url_root; 
    if not _h.endswith('/'): _h += '/'

    def _f(m):
        _x = m.group(0)
        _keep = False
        
        if _bypass_filter:
            _keep = True
        else:
            # Otherwise, check for Arabic
            _s = re.search(r'name=["\'](subs|subtitles)["\'].*?value=["\'](.*?)["\']', _x, re.IGNORECASE)
            if _s:
                _v = _s.group(2).lower(); _ws = _v.replace(',', ' ').replace(';', ' ').split()
                if any(t in _ws for t in _L): _keep = True
                else:
                    for t in _L:
                        if t in _v and (len(t) > 2 or f"{t}-" in _v): _keep = True; break
        
        if _keep:
            _c = re.sub(r'<[^>]*name=["\'](subs|subtitles)["\'][^>]*>', '', _x, flags=re.IGNORECASE)
            _c = re.sub(r'\n\s*\n', '\n', _c)
            def _rw(lm): return f'url="{_h}dl?source={quote(html.unescape(lm.group(1)))}"'
            return re.sub(r'url="([^"]+)"', _rw, _c)
        return ""

    return Response(re.sub(r'<item>.*?</item>', _f, _t, flags=re.DOTALL), mimetype='application/rss+xml')

if __name__ == '__main__': app.run(host='0.0.0.0', port=8000)
