from flask import Flask, request, Response
import requests, re, os, html
from urllib.parse import quote, unquote

app = Flask(__name__)

def _k(n):
    v = os.environ.get(n)
    return v.strip() if v else None

_M = {
    _k("GEEK_API_KEY"): "https://api.nzbgeek.info",
    _k("SLUG_API_KEY"): "https://api.drunkenslug.com",
    _k("PLANET_API_KEY"): "https://api.nzbplanet.net"
}
_M = {k: v for k, v in _M.items() if k}
_L = ["ar", "ara", "arabic", "ar-sa", "sa", "ksa"]

@app.route('/health')
def _h(): return "Alive", 200

@app.route('/dl')
def _d():
    _s = request.args.get('source'); _l = request.args.get('log')
    if not _s: return Response("", 400)
    _u = html.unescape(unquote(_s))
    try:
        _r = requests.get(_u, stream=True, headers={'User-Agent': 'Mozilla/5.0'})
        _r.raise_for_status(); _c = _r.content
        _w = os.environ.get("DISCORD_WEBHOOK")
        if _w and _l == '1':
            try:
                _f = "video.nzb"
                if "Content-Disposition" in _r.headers:
                    _h = _r.headers["Content-Disposition"]
                    _m = re.search(r'filename=["\']?([^"\';]+)["\']?', _h)
                    if _m: _f = _m.group(1)
                requests.post(_w, data={"content": f"**New:** `{_f}`"}, files={"file": (_f, _c)})
            except: pass
        _x = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
        _hd = [(n, v) for (n, v) in _r.raw.headers.items() if n.lower() not in _x]
        return Response(_c, _r.status_code, _hd)
    except Exception as e: return Response(str(e), 502)

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def _c(path):
    _by = False
    if path.startswith('global/'): path = path.replace('global/', '', 1); _by = True
    _pa = request.args.to_dict(); _ik = _pa.get('apikey', '').strip(); _u = _M.get(_ik)
    if not _u: return Response("Auth Error", 401)
    if _pa.get('t') == 'caps':
        try: return Response(requests.get(f"{_u}/api", params=_pa).content, mimetype='application/rss+xml')
        except: return Response("Err", 502)
    _pa['extended'] = '1'
    try:
        _r = requests.get(f"{_u}/api", params=_pa); _r.raise_for_status(); _tx = _r.text
    except Exception as e: return Response(str(e), 502)
    _root = request.url_root
    if not _root.endswith('/'): _root += '/'
    def _sub(m):
        _xml = m.group(0); _k = False
        if _by: _k = True
        else:
            _sm = re.search(r'name=["\'](subs|subtitles)["\'].*?value=["\'](.*?)["\']', _xml, re.IGNORECASE)
            if _sm:
                _v = _sm.group(2).lower(); _ws = _v.replace(',', ' ').replace(';', ' ').split()
                if any(t in _ws for t in _L): _k = True
                else:
                    for t in _L:
                        if t in _v and (len(t) > 2 or f"{t}-" in _v): _k = True; break
        if _k:
            _cl = re.sub(r'<[^>]*name=["\'](subs|subtitles)["\'][^>]*>', '', _xml, flags=re.IGNORECASE)
            _cl = re.sub(r'\n\s*\n', '\n', _cl); _lg = '0' if _by else '1'
            # FIX: use &amp; instead of & for XML compatibility
            def _rl(x): return f'url="{_root}dl?source={quote(html.unescape(x.group(1)))}&amp;log={_lg}"'
            return re.sub(r'url="([^"]+)"', _rl, _cl)
        return ""
    return Response(re.sub(r'<item>.*?</item>', _sub, _tx, flags=re.DOTALL), mimetype='application/rss+xml')

if __name__ == '__main__': app.run(host='0.0.0.0', port=8000)
