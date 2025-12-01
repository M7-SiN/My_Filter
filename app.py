from flask import Flask, request, Response
import requests
import re
import os

app = Flask(__name__)

# --- CONFIGURATION ---
API_KEY_MAP = {
    os.environ.get("GEEK_API_KEY"): "https://api.nzbgeek.info",
    os.environ.get("SLUG_API_KEY"): "https://api.drunkenslug.com",
    os.environ.get("PLANET_API_KEY"): "https://api.nzbplanet.net"
}
API_KEY_MAP = {k: v for k, v in API_KEY_MAP.items() if k}

TARGET_LANGUAGES = ["ar", "ara", "arabic", "ar-sa", "sa", "ksa"]

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

    # 1. Get the RAW text from the indexer with Extended Metadata
    params['extended'] = '1'
    
    try:
        r = requests.get(f"{real_base_url}/api", params=params)
        r.raise_for_status()
        raw_xml = r.text
    except Exception as e:
        return Response(str(e), status=502)

    # --- ROBUST REGEX FILTERING ---
    # Instead of splitting the string manually (which breaks tags),
    # we use re.sub with a callback function to process items in-place.

    def process_item(match):
        item_xml = match.group(0)
        
        # Check for Arabic in the "subs" attribute
        subs_match = re.search(r'name=["\'](subs|subtitles)["\'].*?value=["\'](.*?)["\']', item_xml, re.IGNORECASE)
        
        keep_item = False
        if subs_match:
            val = subs_match.group(2).lower()
            clean_val = val.replace(',', ' ').replace(';', ' ')
            words = clean_val.split()
            
            if any(t in words for t in TARGET_LANGUAGES):
                keep_item = True
            else:
                for t in TARGET_LANGUAGES:
                    if t in val and (len(t) > 2 or f"{t}-" in val):
                        keep_item = True
                        break
        
        if keep_item:
            # Item is Good: Remove the 'subs' tag to fix Stremio UI, but keep everything else
            clean_xml = re.sub(r'<[^>]*name=["\'](subs|subtitles)["\'][^>]*>', '', item_xml, flags=re.IGNORECASE)
            # Optional: Remove empty lines left behind
            clean_xml = re.sub(r'\n\s*\n', '\n', clean_xml)
            return clean_xml
        else:
            # Item is Bad: Return empty string to delete it from the file
            return ""

    # Apply the processor to every <item> block
    # re.DOTALL ensures '.' matches newlines so we capture the full item
    final_output = re.sub(r'<item>.*?</item>', process_item, raw_xml, flags=re.DOTALL)

    return Response(final_output, mimetype='application/rss+xml')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
