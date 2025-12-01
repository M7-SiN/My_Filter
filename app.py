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

    # Bypass Caps Check (Pass through raw)
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

    # --- REGEX FILTERING (The "Better Way") ---
    content = r.text
    
    # 1. Split the XML into Header, Items, and Footer
    # We find where the first <item> starts and where the channel ends
    start_marker = '<item>'
    end_marker = '</channel>'
    
    if start_marker not in content:
        # No results found by indexer, return as is
        return Response(content, mimetype='application/rss+xml')

    # Split into: [Header, Item1, Item2, ... Footer]
    # This allows us to manipulate items without breaking the RSS header definitions
    parts = re.split(r'(<item>)', content)
    
    header = parts[0] # Everything before the first item
    filtered_items = []
    
    # We iterate starting from index 1 because 0 is the header
    # parts[i] is "<item>", parts[i+1] is the content of the item
    for i in range(1, len(parts), 2):
        item_tag = parts[i]      # This is just string "<item>"
        item_body = parts[i+1]   # This is the rest of the item up to next split
        
        full_item_string = item_tag + item_body
        
        # 2. Find the "subs" attribute using Regex
        # Looks for: <newznab:attr name="subs" value="English, Arabic" ... />
        # Capture group 2 contains the value
        subs_match = re.search(r'name=["\'](subs|subtitles)["\'].*?value=["\'](.*?)["\']', full_item_string, re.IGNORECASE)
        
        keep_item = False
        
        if subs_match:
            subs_value = subs_match.group(2).lower()
            
            # Logic: Check if Arabic is in the value
            clean_val = subs_value.replace(',', ' ').replace(';', ' ')
            words = clean_val.split()
            
            if any(t in words for t in TARGET_LANGUAGES):
                keep_item = True
            else:
                # Fallback for things like "ar-sa" inside the string
                for t in TARGET_LANGUAGES:
                    if t in subs_value and (len(t) > 2 or f"{t}-" in subs_value):
                        keep_item = True
                        break

            # 3. Cleanup: If keeping, remove the subs line so Stremio UI is clean
            if keep_item:
                # Remove the entire line containing name="subs"
                # This regex finds the specific <attr> tag for subs and replaces with empty string
                full_item_string = re.sub(r'<[^>]*name=["\'](subs|subtitles)["\'][^>]*>', '', full_item_string, flags=re.IGNORECASE)
                filtered_items.append(full_item_string)

    # 4. Rebuild the XML
    # If the last item split included the footer (</channel>...), we need to be careful not to duplicate or lose it.
    # The regex split usually leaves the footer attached to the last item body or as a separate part.
    # Simpler approach: Join valid items, then attach footer.
    
    # Ideally, we reconstruct exactly what we split.
    # But simple split might leave footer in the last element.
    
    # Safer Rebuild Strategy:
    # Check if footer exists in the last filtered item (if we kept the last one). 
    # If we deleted the last item from the original list, we lost the footer.
    # We must extract the footer from the original content first.
    
    footer_index = content.rfind('</channel>')
    if footer_index != -1:
        footer = content[footer_index:]
        # Strip footer from the last item processed in the loop to avoid duplication
        # (The regex split approach makes this tricky, let's refine the loop logic above)
    
    # --- REFINED REBUILD LOGIC ---
    # Let's use a safer split pattern that separates items cleanly
    item_blocks = re.findall(r'(<item>.*?</item>)', content, re.DOTALL)
    
    final_items = []
    for block in item_blocks:
        # Check for subs
        subs_match = re.search(r'name=["\'](subs|subtitles)["\'].*?value=["\'](.*?)["\']', block, re.IGNORECASE)
        
        if subs_match:
            val = subs_match.group(2).lower()
            clean_val = val.replace(',', ' ').replace(';', ' ')
            words = clean_val.split()
            
            is_arabic = any(t in words for t in TARGET_LANGUAGES)
            if not is_arabic:
                 for t in TARGET_LANGUAGES:
                    if t in val and (len(t) > 2 or f"{t}-" in val):
                        is_arabic = True
                        break
            
            if is_arabic:
                # Remove the subs tag for clean UI
                clean_block = re.sub(r'<[^>]*name=["\'](subs|subtitles)["\'][^>]*>', '', block, flags=re.IGNORECASE)
                final_items.append(clean_block)

    # Reconstruct: Header + All Kept Items + Footer
    # We locate the first <item> to find where header ends
    first_item_pos = content.find('<item>')
    last_item_end_pos = content.rfind('</item>') + 7
    
    if first_item_pos != -1:
        real_header = content[:first_item_pos]
        real_footer = content[last_item_end_pos:]
        final_xml = real_header + "".join(final_items) + real_footer
        return Response(final_xml, mimetype='application/rss+xml')
    else:
        # If structure is weird, return original
        return Response(content, mimetype='application/rss+xml')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
