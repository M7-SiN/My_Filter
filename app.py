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

    # 2. Split the XML into Header and Items
    # We assume the first <item> marks the start of the content
    first_item_index = raw_xml.find('<item>')
    
    if first_item_index == -1:
        # No items found, return raw response (likely empty results or error)
        return Response(raw_xml, mimetype='application/rss+xml')

    # Separate the Header (RSS definitions) from the Body
    header = raw_xml[:first_item_index]
    body = raw_xml[first_item_index:]

    # 3. Extract all <item>...</item> blocks using Regex
    # re.DOTALL makes the dot (.) match newlines
    items = re.findall(r'(<item>.*?</item>)', body, re.DOTALL)
    
    # We also need to capture the footer (</channel></rss>)
    # It's whatever is left after the last item
    last_item_end = body.rfind('</item>') + 7
    footer = body[last_item_end:]

    filtered_items = []

    for item_xml in items:
        keep_item = False
        
        # 4. Check for Arabic in the "subs" attribute
        # We look for: name="subs" ... value="...Arabic..."
        subs_match = re.search(r'name=["\'](subs|subtitles)["\'].*?value=["\'](.*?)["\']', item_xml, re.IGNORECASE)
        
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

        # 5. If we keep it, scrub the subtitle line to match "Standard" output
        if keep_item:
            # This regex removes the entire <newznab:attr name="subs" ... /> line
            # It leaves the size and enclosure tags 100% untouched.
            clean_xml = re.sub(r'<.*?name=["\'](subs|subtitles)["\'].*?/>', '', item_xml, flags=re.IGNORECASE)
            filtered_items.append(clean_xml)

    # 6. Rebuild the final XML string
    final_output = header + "".join(filtered_items) + footer

    return Response(final_output, mimetype='application/rss+xml')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
