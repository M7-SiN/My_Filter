from flask import Flask, request, Response
import requests
import xml.etree.ElementTree as ET
import os

app = Flask(__name__)

# --- CONFIGURATION ---
API_KEY_MAP = {
    os.environ.get("GEEK_API_KEY"): "https://api.nzbgeek.info"
}
# Clean up empty keys
API_KEY_MAP = {k: v for k, v in API_KEY_MAP.items() if k}

TARGET_LANGUAGES = ["ar", "ara", "arabic", "ar-sa", "sa",]
TARGET_ATTR_NAMES = ["subs", "subs ", "subtitles", "language"]

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
    params = request.args.to_dict()
    incoming_key = params.get('apikey', '').strip()
    
    # 1. Identify Indexer
    real_base_url = API_KEY_MAP.get(incoming_key)
    
    if not real_base_url:
        return Response("Error: API Key not recognized. Check Environment Variables.", status=401)

    # 2. Bypass Capabilities Check
    if params.get('t') == 'caps':
        try:
            r = requests.get(f"{real_base_url}/api", params=params)
            return Response(r.content, mimetype='application/rss+xml')
        except:
            return Response("Indexer Down", status=502)

    # 3. Force Extended Data
    params['extended'] = '1'
    
    # 4. Forward Request
    try:
        r = requests.get(f"{real_base_url}/api", params=params)
    except Exception as e:
        return Response(str(e), status=502)

    # 5. Filter Logic
    try:
        root = ET.fromstring(r.content)
        channel = root.find('channel')
        items = channel.findall('item') if channel is not None else []
        
        for item in items:
            keep_item = False
            for child in item:
                if child.tag.endswith('attr'):
                    name = child.get('name', '').lower()
                    val = child.get('value', '').lower()
                    
                    if name in TARGET_ATTR_NAMES:
                        clean_val = val.replace(',', ' ').replace(';', ' ')
                        words = clean_val.split()
                        
                        if any(t in words for t in TARGET_LANGUAGES):
                            keep_item = True
                            break
                        for t in TARGET_LANGUAGES:
                            if t in val and (len(t) > 2 or f"{t}-" in val):
                                keep_item = True
                                break
            
            if not keep_item:
                channel.remove(item)
                
        return Response(ET.tostring(root), mimetype='application/rss+xml')

    except:
        return Response(r.content, status=r.status_code)

if __name__ == '__main__':
    # This allows you to run it locally with 'python app.py' if needed
    app.run(host='0.0.0.0', port=8000)