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

# Filter Settings
TARGET_LANGUAGES = ["ar", "ara", "arabic", "ar-sa", "sa", "ksa"]
CHECK_ATTRS = ["subs", "subs ", "subtitles", "language"]
HIDE_ATTRS = ["subs", "subs ", "subtitles"]

# Register namespace to help, but we will double-check with string replacement later
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

    if params.get('t') == 'caps':
        try:
            r = requests.get(f"{real_base_url}/api", params=params)
            return Response(r.content, mimetype='application/rss+xml')
        except:
            return Response("Indexer Down", status=502)

    # Force Extended
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

                    # Mark for deletion
                    if name in HIDE_ATTRS:
                        tags_to_delete.append(child)

                    # Check Language
                    if name in CHECK_ATTRS:
                        clean_val = val.replace(',', ' ').replace(';', ' ')
                        words = clean_val.split()
                        if any(t in words for t in TARGET_LANGUAGES):
                            keep_item = True
                        for t in TARGET_LANGUAGES:
                            if t in val and (len(t) > 2 or f"{t}-" in val):
                                keep_item = True

            if not keep_item:
                channel.remove(item)
            else:
                for tag in tags_to_delete:
                    try:
                        item.remove(tag)
                    except:
                        pass

        # Generate the XML string
        xml_str = ET.tostring(root, encoding='utf-8').decode('utf-8')

        # --- FINAL SAFETY PATCH ---
        # Python sometimes ignores register_namespace and uses 'ns0:attr'.
        # We manually force it back to 'newznab:attr' so Stremio recognizes the size.
        xml_str = xml_str.replace('ns0:attr', 'newznab:attr')
        xml_str = xml_str.replace('ns0:response', 'newznab:response')
        
        # Ensure the namespace definition exists in the header if it was lost
        if 'xmlns:newznab' not in xml_str:
            xml_str = xml_str.replace('<rss', '<rss xmlns:newznab="http://www.newznab.com/DTD/2010/feeds/attributes/"')

        return Response(xml_str.encode('utf-8'), mimetype='application/rss+xml')

    except Exception as e:
        # Fallback: return original content if parsing broke
        return Response(r.content, status=r.status_code)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)


