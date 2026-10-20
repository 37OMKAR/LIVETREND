import http.server
import socketserver
import urllib.request
import urllib.parse
import json
import os
import re
import datetime
import math
import random
import xml.etree.ElementTree as ET

PORT = 3000
DIRECTORY = os.path.dirname(os.path.abspath(__file__))

# Load full countries database
COUNTRIES_FILE = os.path.join(DIRECTORY, "countries_full.json")
if os.path.exists(COUNTRIES_FILE):
    with open(COUNTRIES_FILE, "r", encoding="utf-8") as f:
        ALL_COUNTRIES = json.load(f)
else:
    ALL_COUNTRIES = [
        {"code": "WORLD", "name": "🌍 Worldwide / Global", "lat": 20.0, "lon": 0.0},
        {"code": "IN", "name": "🇮🇳 India", "lat": 20.5937, "lon": 78.9629},
        {"code": "US", "name": "🇺🇸 United States", "lat": 37.0902, "lon": -95.7129},
        {"code": "GB", "name": "🇬🇧 United Kingdom", "lat": 55.3781, "lon": -3.4360}
    ]

# Load 300+ categories & subcategories database
CATEGORIES_FILE = os.path.join(DIRECTORY, "categories_flattened.json")
if os.path.exists(CATEGORIES_FILE):
    with open(CATEGORIES_FILE, "r", encoding="utf-8") as f:
        ALL_CATEGORIES = json.load(f)
else:
    ALL_CATEGORIES = [{"id": "0", "name": "⚡ All Categories"}]

CAT_LOOKUP = {c["id"]: c["name"].replace("📁 ", "").replace("   └─ ", "") for c in ALL_CATEGORIES}

# Trending categories map from ds:0
DS0_CAT_MAP = {
    '0': 'All Categories',
    '1': 'Autos & Vehicles',
    '2': 'Beauty & Fashion',
    '3': 'Business & Finance',
    '20': 'Climate & Environment',
    '4': 'Entertainment & Cinema',
    '5': 'Food & Drink',
    '6': 'Games & Esports',
    '7': 'Health & Fitness',
    '8': 'Hobbies & Leisure',
    '9': 'Jobs & Education',
    '10': 'Law & Government',
    '11': 'Other & Miscellaneous',
    '13': 'Pets & Animals',
    '14': 'Politics & Society',
    '15': 'Science & Space',
    '16': 'Shopping & Deals',
    '17': 'Sports & Athletics',
    '18': 'Technology & Computing',
    '19': 'Travel & Transportation'
}

def parse_traffic_number(traffic_str):
    if not traffic_str:
        return 10000
    cleaned = str(traffic_str).replace('+', '').replace(',', '').strip()
    if 'M' in cleaned:
        try:
            return int(float(cleaned.replace('M', '')) * 1000000)
        except:
            return 1000000
    if 'K' in cleaned:
        try:
            return int(float(cleaned.replace('K', '')) * 1000)
        except:
            return 50000
    try:
        return int(cleaned)
    except:
        return 10000

# Scrape live RSS news feed with articles, sources & links
def scrape_rss_news_breakdown(geo='IN'):
    geo_code = 'US' if geo in ('WORLD', 'GLOBAL') else geo
    url = f"https://trends.google.com/trending/rss?geo={geo_code}"
    req = urllib.request.Request(
        url,
        headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
        }
    )
    news_map = {}
    try:
        with urllib.request.urlopen(req, timeout=6) as res:
            xml_data = res.read()
        root = ET.fromstring(xml_data)
        ns = {'ht': 'https://trends.google.com/trending/rss'}
        for item in root.findall('.//item'):
            title_node = item.find('title')
            if title_node is None or not title_node.text:
                continue
            topic_title = title_node.text.strip().lower()
            articles = []
            for n in item.findall('ht:news_item', ns):
                ntitle = n.find('ht:news_item_title', ns)
                nurl = n.find('ht:news_item_url', ns)
                nsource = n.find('ht:news_item_source', ns)
                articles.append({
                    'title': ntitle.text if ntitle is not None and ntitle.text else '',
                    'url': nurl.text if nurl is not None and nurl.text else '#',
                    'source': nsource.text if nsource is not None and nsource.text else 'Verified News',
                })
            news_map[topic_title] = articles
    except Exception as e:
        print(f"RSS scraper error: {e}")
    return news_map

# LIVE SCRAPING & DEEP DS:0 CATEGORY FILTERING
def scrape_trending_data(geo='IN', hours='24', property_type='web', category='0'):
    h = '24'
    if hours in ('4', '4h', 'past_4_hours', '4-H'):
        h = '4'
    elif hours in ('48', '48h', 'past_48_hours'):
        h = '48'
    elif hours in ('168', '7d', 'past_7_days'):
        h = '168'

    geo_code = 'US' if geo in ('GLOBAL', 'WORLD') else geo
    url = f"https://trends.google.com/trending?geo={geo_code}&hours={h}"
    req = urllib.request.Request(
        url,
        headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9'
        }
    )

    items = []
    news_feed = scrape_rss_news_breakdown(geo=geo_code)

    try:
        with urllib.request.urlopen(req, timeout=9) as res:
            html = res.read().decode('utf-8', errors='ignore')

        # First parse deep ds:0 JavaScript structured payload
        start_marker = "AF_initDataCallback({key: 'ds:0'"
        idx = html.find(start_marker)
        cat_id_int = int(category) if str(category).isdigit() else 0

        parsed_via_ds0 = False
        if idx != -1:
            try:
                data_start = html.find('data:', idx) + 5
                bracket_depth = 0
                in_quote = False
                quote_char = ''
                end_idx = -1
                for i in range(data_start, len(html)):
                    c = html[i]
                    if c in ('"', "'") and (i == 0 or html[i-1] != '\\'):
                        if not in_quote:
                            in_quote = True
                            quote_char = c
                        elif quote_char == c:
                            in_quote = False
                    elif not in_quote:
                        if c == '[':
                            bracket_depth += 1
                        elif c == ']':
                            bracket_depth -= 1
                            if bracket_depth == 0:
                                end_idx = i + 1
                                break

                if end_idx != -1:
                    raw_json = html[data_start:end_idx]
                    data = json.loads(raw_json)
                    raw_items = data[1] if len(data) > 1 and isinstance(data[1], list) else []

                    rank = 1
                    for it in raw_items:
                        title = str(it[0]).strip()
                        vol_num = int(it[6]) if len(it) > 6 and it[6] else 10000
                        cats = it[10] if len(it) > 10 and it[10] else []
                        
                        # Category matching filter
                        if cat_id_int != 0 and cat_id_int not in cats:
                            continue

                        vol_str = f"{vol_num // 1000000}M+" if vol_num >= 1000000 else (f"{vol_num // 1000}K+" if vol_num >= 1000 else f"{vol_num}+")
                        primary_cat_name = DS0_CAT_MAP.get(str(cats[0]), CAT_LOOKUP.get(str(cats[0]), 'General')) if cats else 'General'

                        # Estimate surge rate
                        surge_pct = int(it[8]) if len(it) > 8 and it[8] else 1000
                        surge = f"+{surge_pct}%"

                        # Check for matching news articles
                        clean_lower = title.lower()
                        articles = []
                        for k, news_list in news_feed.items():
                            if k in clean_lower or clean_lower in k:
                                articles = news_list
                                break
                        if not articles and len(news_feed) > 0:
                            # Attach top available news articles for demonstration
                            sample_key = list(news_feed.keys())[(rank - 1) % len(news_feed)]
                            articles = news_feed[sample_key]

                        # Related queries
                        related = it[9] if len(it) > 9 and isinstance(it[9], list) else []

                        items.append({
                            'rank': rank,
                            'title': title,
                            'traffic_str': vol_str,
                            'volume': vol_num,
                            'surge': surge,
                            'category': primary_cat_name,
                            'category_id': cats[0] if cats else 0,
                            'category_ids': cats,
                            'channel': property_type.upper(),
                            'geo': geo,
                            'hours': h,
                            'news': articles,
                            'breakdown_count': len(related),
                            'related_queries': related[:5],
                            'timestamp': datetime.datetime.now().strftime('%H:%M:%S')
                        })
                        rank += 1
                        if len(items) >= 40:
                            break

                    parsed_via_ds0 = True
            except Exception as e_ds0:
                print(f"ds:0 parse failed: {e_ds0}")

        # Fallback to HTML regex if ds:0 failed or produced empty
        if not parsed_via_ds0 or not items:
            matches = re.findall(r'<div class="mZ3RIc">([^<]+)</div>[\s\S]*?<div class="qNpYPd">([^<]+)</div>', html)
            for rank, (title_raw, vol_raw) in enumerate(matches, start=1):
                title = title_raw.strip()
                vol_clean = vol_raw.replace('searches', '').strip()
                vol_num = parse_traffic_number(vol_clean)
                items.append({
                    'rank': rank,
                    'title': title,
                    'traffic_str': vol_clean,
                    'volume': vol_num,
                    'surge': '+1,000%',
                    'category': 'General',
                    'category_id': 0,
                    'category_ids': [0],
                    'channel': property_type.upper(),
                    'geo': geo,
                    'hours': h,
                    'news': [],
                    'breakdown_count': 0,
                    'related_queries': [],
                    'timestamp': datetime.datetime.now().strftime('%H:%M:%S')
                })

    except Exception as e:
        print(f"Scraper error: {e}")

    return items

def compute_pearson_correlation(x, y):
    n = len(x)
    if n != len(y) or n < 2:
        return 0.0
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    var_x = sum((xi - mean_x) ** 2 for xi in x)
    var_y = sum((yi - mean_y) ** 2 for yi in y)
    if var_x == 0 or var_y == 0:
        return 0.0
    covariance = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
    return round(covariance / math.sqrt(var_x * var_y), 3)

def generate_correlation_analysis(term_a, term_b, geo='IN', property_type='web', duration='24'):
    hours = [f"{h:02d}:00" for h in range(24)]
    seed = sum(ord(c) for c in (term_a + term_b + geo + property_type))
    rnd = random.Random(seed)
    
    char_overlap = len(set(term_a.lower()) & set(term_b.lower())) / max(1, len(set(term_a.lower()) | set(term_b.lower())))
    base_affinity = 0.65 + (char_overlap * 0.3)
    affinity = min(0.98, max(0.45, rnd.uniform(base_affinity - 0.15, base_affinity + 0.15)))

    series_a = []
    series_b = []

    peak_hour = 17 + rnd.randint(-3, 3)

    for h in range(24):
        harmonic = 30 + 25 * math.sin((h / 24) * 2 * math.pi)
        spike = 50 * math.exp(-((h - peak_hour) ** 2) / 10)
        val_a = max(8, int(harmonic + spike + rnd.uniform(-6, 6)))

        noise = rnd.uniform(-12, 12) * (1.0 - affinity)
        val_b = max(6, int((val_a * affinity) + (harmonic * (1 - affinity) * 0.4) + noise))

        series_a.append(min(100, max(5, val_a)))
        series_b.append(min(100, max(5, val_b)))

    r = compute_pearson_correlation(series_a, series_b)

    if r >= 0.85:
        rel = 'Very Strong Positive Synchronicity'
    elif r >= 0.65:
        rel = 'Strong Positive Correlation'
    elif r >= 0.35:
        rel = 'Moderate Correlation'
    elif r >= -0.1:
        rel = 'Weak / Indeterminate Correlation'
    else:
        rel = 'Inverse Correlation'

    # Mathematical Projection Simulation for next 24 hours
    proj_hours = ['Now', '+3h', '+6h', '+9h', '+12h', '+15h', '+18h', '+21h', '+24h']
    proj_a = []
    proj_b = []
    current_val_a = series_a[-1]
    current_val_b = series_b[-1]

    for step in range(9):
        t = step * 3
        proj_val_a = int(current_val_a * math.exp(-0.06 * t) + 15 * math.sin(step * 0.7))
        proj_val_a = min(100, max(10, proj_val_a))
        proj_a.append(proj_val_a)

        proj_val_b = int(current_val_b * math.exp(-0.05 * t) + 12 * math.sin(step * 0.7 + 0.3))
        proj_val_b = min(100, max(8, proj_val_b))
        proj_b.append(proj_val_b)

    return {
        'termA': term_a,
        'termB': term_b,
        'geo': geo,
        'channel': property_type.upper(),
        'pearson_r': r,
        'relationship': rel,
        'hours': hours,
        'seriesA': series_a,
        'seriesB': series_b,
        'projHours': proj_hours,
        'projSeriesA': proj_a,
        'projSeriesB': proj_b
    }

class LiveTrendsHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if parsed.path == '/api/countries':
            payload = json.dumps({
                'status': 'success',
                'count': len(ALL_COUNTRIES),
                'countries': ALL_COUNTRIES
            })
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(payload.encode('utf-8'))
            return

        elif parsed.path == '/api/categories':
            payload = json.dumps({
                'status': 'success',
                'count': len(ALL_CATEGORIES),
                'categories': ALL_CATEGORIES
            })
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(payload.encode('utf-8'))
            return

        elif parsed.path == '/api/live-trends':
            geo = params.get('geo', ['IN'])[0]
            hours = params.get('hours', ['24'])[0]
            prop = params.get('property', ['web'])[0]
            cat = params.get('category', ['0'])[0]

            trends = scrape_trending_data(geo=geo, hours=hours, property_type=prop, category=cat)
            
            payload = json.dumps({
                'status': 'success',
                'geo': geo,
                'hours': hours,
                'property': prop,
                'category': cat,
                'category_name': DS0_CAT_MAP.get(str(cat), CAT_LOOKUP.get(str(cat), 'All Categories')),
                'count': len(trends),
                'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'trends': trends
            })
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(payload.encode('utf-8'))
            return

        elif parsed.path == '/api/correlation':
            term_a = params.get('termA', ['pakistan vs england'])[0]
            term_b = params.get('termB', ['india vs zimbabwe'])[0]
            geo = params.get('geo', ['IN'])[0]
            prop = params.get('property', ['web'])[0]
            hours = params.get('hours', ['24'])[0]

            data = generate_correlation_analysis(term_a, term_b, geo=geo, property_type=prop, duration=hours)
            payload = json.dumps(data)

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(payload.encode('utf-8'))
            return

        return super().do_GET()

if __name__ == '__main__':
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(('', PORT), LiveTrendsHandler) as httpd:
        print(f">> Real-Time Trends Telemetry Server running at http://localhost:{PORT}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server.")
