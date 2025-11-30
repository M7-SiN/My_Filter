from flask import Flask, request, Response
import requests
import xml.etree.ElementTree as ET
import os

app = Flask(__name__)

# --- CONFIGURATION ---
API_KEY_MAP = {
    os.environ.get("GEEK_API_KEY"): "https://api.nzbgeek.info",
    os.environ.get("SLUG_API_KEY"): "https://api.drunkenslug.com",
    os.environ.get("PLANET_API_KEY"): "https://api.nzbplanet.net"
}
API_KEY_MAP = {k: v for k, v in API_KEY_MAP.items() if k}

# 1. Languages to KEEP (Filter Logic)
TARGET_LANGUAGES = ["ar", "ara", "arabic", "ar-sa", "sa", "ksa"]

# 2. Attributes to READ to find those languages
CHECK_ATTRS = ["subs", "subs ", "subtitles", "language"]

# 3. Attributes to DELETE from the final output (Cleanup)
# We remove these so the result looks like a "Regular" search to Stremio
HIDE_ATTRS = ["subs", "subs ", "subtitles"]

# --- NAMESPACE FIX ---
try:
    ET.register_namespace('newznab', 'http://www.newznab.com/DTD/2010/feeds/attributes/')
    ET.register_namespace('atom', 'http://www.w3.org/2005/Atom')
except:
    pass

@app.route('/health')
def health_check():
    return "Alive", 200

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
    params = request.args.to_dict()
    incoming_key = params.get('apikey', '').strip()
    
    real_base_url = API_KEY_MAP.get(incoming_key)
    if not real_base_url:
        return Response("Error: API Key not recognized.", status=401)

    # Bypass Caps
    if params.get('t') == 'caps':
        try:
            r = requests.get(f"{real_base_url}/api", params=params)
            return Response(r.content, mimetype='application/rss+xml')
        except:
            return Response("Indexer Down", status=502)

    # We MUST force extended=1 to perform the check
    params['extended'] = '1'
    
    try:
        r = requests.get(f"{real_base_url}/api", params=params)
        r.raise_for_status()
    except Exception as e:
        return Response(str(e), status=502)

    try:
        root = ET.fromstring(r.content)
        channel = root.find('channel')
        items = channel.findall('item') if channel is not None else []
        
        for item in items:
            keep_item = False
            tags_to_delete = [] 

            for child in item:
                if child.tag.endswith('attr'):
                    name = child.get('name', '').lower()
                    val = child.get('value', '').lower()

                    # 1. Mark for deletion if it's a subtitle tag
                    # We do this so Stremio doesn't see the messy subtitle list
                    if name in HIDE_ATTRS:
                        tags_to_delete.append(child)

                    # 2. Filter Logic (Check if it contains Arabic)
                    if name in CHECK_ATTRS:
                        clean_val = val.replace(',', ' ').replace(';', ' ')
                        words = clean_val.split()
                        
                        if any(t in words for t in TARGET_LANGUAGES):
                            keep_item = True
                        
                        # Loose Match
                        for t in TARGET_LANGUAGES:
                            if t in val and (len(t) > 2 or f"{t}-" in val):
                                keep_item = True

            # DECISION TIME
            if not keep_item:
                # No Arabic found? Delete the whole item.
                channel.remove(item)
            else:
                # Arabic found? Keep item, but remove the subtitle tags to clean up the view.
                # 'audiolanguage' and 'size' are NOT in HIDE_ATTRS, so they stay.
                for tag in tags_to_delete:
                    try:
                        item.remove(tag)
                    except:
                        pass
                
        return Response(ET.tostring(root, encoding='utf-8'), mimetype='application/rss+xml')

    except Exception as e:
        return Response(r.content, status=r.status_code)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)


