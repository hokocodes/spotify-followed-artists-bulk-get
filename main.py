from flask import Flask, request, redirect, session, url_for, jsonify, Response
import requests
import base64
import os
import re
from urllib.parse import urlencode
from ddgs import DDGS
import json
from dotenv import load_dotenv
from bs4 import BeautifulSoup
import urllib.parse

# #region agent log
def debug_log(location, message, data, hypothesis_id=None, run_id="initial"):
    try:
        log_entry = {
            "id": f"log_{int(__import__('time').time() * 1000)}",
            "timestamp": int(__import__('time').time() * 1000),
            "location": location,
            "message": message,
            "data": data,
            "runId": run_id
        }
        if hypothesis_id:
            log_entry["hypothesisId"] = hypothesis_id
        with open(r'c:\Users\hokop\Documents\GitHub\spotify-followed-artists-bulk-get\.cursor\debug.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry) + '\n')
    except Exception:
        pass
# #endregion

load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)  # Secret key for session management

# Replace these with your Spotify app credentials
CLIENT_ID = os.getenv('CLIENT_ID')
CLIENT_SECRET = os.getenv('CLIENT_SECRET')
REDIRECT_URI = 'http://127.0.0.1:5000/callback'  # Update to match your setup
# Spotify API endpoints
AUTH_URL = 'https://accounts.spotify.com/authorize'
TOKEN_URL = 'https://accounts.spotify.com/api/token'
FOLLOWED_ARTISTS_URL = 'https://api.spotify.com/v1/me/following'
# Scopes required
SCOPES = 'user-follow-read'

@app.route('/')
def index():
    return '<a href="/login">Login with Spotify</a>'

@app.route('/login')
def login():
    params = {
        'client_id': CLIENT_ID,
        'response_type': 'code',
        'redirect_uri': REDIRECT_URI,
        'scope': SCOPES,
        'show_dialog': 'true'
    }
    auth_query = urlencode(params)
    return redirect(f'{AUTH_URL}?{auth_query}')

@app.route('/callback')
def callback():
    code = request.args.get('code')
    if not code:
        return 'Error: No code provided', 400

    auth_header = base64.b64encode(f'{CLIENT_ID}:{CLIENT_SECRET}'.encode('utf-8')).decode('utf-8')
    headers = {
        'Authorization': f'Basic {auth_header}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    data = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': REDIRECT_URI
    }
    response = requests.post(TOKEN_URL, headers=headers, data=data)
    
    if response.status_code != 200:
        return f'Error getting token: {response.text}', 500
    
    token_info = response.json()
    session['access_token'] = token_info['access_token']
    
    return redirect(url_for('followed_artists'))

def get_spotify_artists(access_token):
    headers = {
        'Authorization': f'Bearer {access_token}'
    }
    
    all_artists = []
    next_url = f'{FOLLOWED_ARTISTS_URL}?type=artist&limit=50'
    
    while next_url:
        response = requests.get(next_url, headers=headers)
        
        if response.status_code != 200:
            return None, f'Error fetching followed artists: {response.text}'
        
        data = response.json()
        artists = data['artists']['items']
        all_artists.extend(artists)
        
        next_url = data['artists'].get('next')
    
    return all_artists, None

def get_instagram_data(artist_name, embed_images=False):
    try:
        query = f'{artist_name} instagram'
        
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=10))
        
        instagram_link = None
        for result in results:
            link = result.get("href", "")
            if "instagram.com" in link and "/p/" not in link and "/reel/" not in link:
                instagram_link = link.rstrip("/")
                break
        
        if instagram_link:
            
            username = instagram_link.rstrip('/').split('/')[-1]

            try:
                ig_headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                }

                ig_response = requests.get(
                    f'https://www.instagram.com/{username}/',
                    headers=ig_headers
                )

                # #region agent log
                debug_log(f"main.py:{118}", "Instagram response status", {"status_code": ig_response.status_code, "username": username, "response_length": len(ig_response.text) if ig_response.status_code == 200 else 0}, "D", "initial")
                # #endregion

                bio = 'No bio available'
                followers = 0
                profile_pic_url = ''

                if ig_response.status_code == 200:
                    soup = BeautifulSoup(ig_response.text, 'html.parser')

                    # Try meta tags (og:description often has follower count and bio)
                    og_desc = soup.find("meta", property="og:description")
                    if og_desc and og_desc.get("content"):
                        desc = og_desc["content"]
                        # Format: "123K Followers, 456 Following, 789 Posts - See Instagram photos and videos from Name (@username)"
                        follower_match = re.search(r'([\d,.]+[KkMm]?)\s*Followers', desc)
                        if follower_match:
                            count_str = follower_match.group(1).replace(',', '')
                            if count_str.upper().endswith('K'):
                                followers = int(float(count_str[:-1]) * 1000)
                            elif count_str.upper().endswith('M'):
                                followers = int(float(count_str[:-1]) * 1000000)
                            else:
                                followers = int(float(count_str))
                        
                        # Extract bio from the description (after the dash)
                        bio_match = re.search(r'[-–]\s*(.+)', desc)
                        if bio_match:
                            bio = bio_match.group(1).strip()
                            # Remove "See Instagram photos and videos from ..." prefix
                            bio = re.sub(r'^See Instagram photos and videos from .+?\(@\w+\)\s*', '', bio).strip()
                            if not bio:
                                bio = bio_match.group(1).strip()

                    # If followers still 0, try to find in JSON-LD structured data
                    if followers == 0:
                        json_scripts = soup.find_all('script', type='application/ld+json')
                        for script in json_scripts:
                            try:
                                data = json.loads(script.string)
                                if isinstance(data, dict):
                                    # Look for follower count in various possible locations
                                    if 'interactionStatistic' in data:
                                        for stat in data.get('interactionStatistic', []):
                                            if isinstance(stat, dict) and stat.get('interactionType', {}).get('@type') == 'https://schema.org/FollowAction':
                                                count = stat.get('userInteractionCount', 0)
                                                if count:
                                                    followers = int(count)
                                                    break
                            except (json.JSONDecodeError, ValueError, AttributeError):
                                continue

                    # If followers still 0, try searching in the page text/HTML
                    if followers == 0:
                        page_text = ig_response.text
                        # Look for patterns like "1,234 followers" or "1.2M followers" in the HTML
                        # Try multiple patterns
                        patterns = [
                            r'"followers":\s*(\d+)',  # JSON format
                            r'followers["\']?\s*:\s*["\']?(\d+)',  # Various JSON-like formats
                            r'(\d+(?:[.,]\d+)?[KkMm]?)\s*followers',  # Text format
                            r'(\d+(?:[.,]\d+)?[KkMm]?)\s*Followers',  # Capitalized
                        ]
                        for pattern in patterns:
                            match = re.search(pattern, page_text, re.IGNORECASE)
                            if match:
                                count_str = match.group(1).replace(',', '')
                                try:
                                    if count_str.upper().endswith('K'):
                                        followers = int(float(count_str[:-1]) * 1000)
                                    elif count_str.upper().endswith('M'):
                                        followers = int(float(count_str[:-1]) * 1000000)
                                    else:
                                        # Try to parse as float first to handle decimals, then convert to int
                                        followers = int(float(count_str))
                                    if followers > 0:
                                        break
                                except (ValueError, AttributeError):
                                    continue

                    # Try multiple methods to get profile picture (prioritize actual user profile pics, not logos)
                    page_text = ig_response.text
                    
                    # Method 1: Look for Instagram's internal data structures (most reliable)
                    # Instagram often embeds user data in script tags
                    script_patterns = [
                        r'window\._sharedData\s*=\s*({.+?});',
                        r'<script type="application/json"[^>]*data-sjs>({.+?})</script>',
                        r'<script type="application/json"[^>]*>({.+?})</script>',
                        r'"ProfilePage":\s*\[({.+?})\]',  # Direct ProfilePage pattern
                    ]
                    
                    for pattern in script_patterns:
                        matches = re.findall(pattern, page_text, re.DOTALL)
                        for match in matches:
                            try:
                                data = json.loads(match)
                                # Navigate through Instagram's data structure
                                if isinstance(data, dict):
                                    # Try different possible paths in Instagram's data structure
                                    paths_to_try = [
                                        ['entry_data', 'ProfilePage', 0, 'graphql', 'user', 'profile_pic_url_hd'],
                                        ['entry_data', 'ProfilePage', 0, 'graphql', 'user', 'profile_pic_url'],
                                        ['graphql', 'user', 'profile_pic_url_hd'],
                                        ['graphql', 'user', 'profile_pic_url'],
                                        ['user', 'profile_pic_url_hd'],
                                        ['user', 'profile_pic_url'],
                                        ['props', 'pageProps', 'user', 'profile_pic_url_hd'],
                                        ['props', 'pageProps', 'user', 'profile_pic_url'],
                                    ]
                                    
                                    for path in paths_to_try:
                                        current = data
                                        try:
                                            for key in path:
                                                if isinstance(current, list) and isinstance(key, int):
                                                    if key < len(current):
                                                        current = current[key]
                                                    else:
                                                        break
                                                elif isinstance(current, dict):
                                                    current = current.get(key)
                                                else:
                                                    break
                                                
                                                if current is None:
                                                    break
                                            
                                            if isinstance(current, str) and current.startswith('http'):
                                                # Filter out logos
                                                if not any(exclude in current.lower() for exclude in ['logo', 'icon', 'brand', 'default']):
                                                    profile_pic_url = current
                                                    break
                                        except (KeyError, IndexError, TypeError):
                                            continue
                                    
                                    if profile_pic_url:
                                        # #region agent log
                                        debug_log(f"main.py:{251}", "Found profile_pic_url via path traversal", {"method": "path_traversal", "path": str(path), "url": profile_pic_url[:100]}, "A", "initial")
                                        # #endregion
                                        break
                                    
                                    # Also try to recursively search for profile_pic_url in the data
                                    def find_profile_pic(obj, depth=0):
                                        if depth > 10:  # Prevent infinite recursion
                                            return None
                                        if isinstance(obj, dict):
                                            for key, value in obj.items():
                                                if 'profile_pic_url' in str(key).lower():
                                                    if isinstance(value, str) and value.startswith('http'):
                                                        if not any(exclude in value.lower() for exclude in ['logo', 'icon', 'brand', 'default']):
                                                            return value
                                                result = find_profile_pic(value, depth + 1)
                                                if result:
                                                    return result
                                        elif isinstance(obj, list):
                                            for item in obj:
                                                result = find_profile_pic(item, depth + 1)
                                                if result:
                                                    return result
                                        return None
                                    
                                    if not profile_pic_url:
                                        found_url = find_profile_pic(data)
                                        if found_url:
                                            profile_pic_url = found_url
                                            # #region agent log
                                            debug_log(f"main.py:{282}", "Found profile_pic_url via recursive search", {"method": "recursive_search", "url": profile_pic_url[:100]}, "A", "initial")
                                            # #endregion
                                            
                            except (json.JSONDecodeError, ValueError, AttributeError):
                                continue
                        if profile_pic_url:
                            break
                    
                    # Method 2: Search for profile_pic_url in script tags (more specific patterns)
                    if not profile_pic_url:
                        # Look for script tags that might contain user data
                        script_tags = soup.find_all('script')
                        for script in script_tags:
                            if script.string:
                                script_text = script.string
                                # Look for profile_pic_url patterns in script content
                                img_patterns = [
                                    r'"profile_pic_url_hd":\s*"([^"]+)"',  # HD version first
                                    r'"profile_pic_url":\s*"([^"]+)"',
                                    r'profile_pic_url_hd["\']?\s*:\s*["\']([^"\']+)["\']',
                                    r'profile_pic_url["\']?\s*:\s*["\']([^"\']+)["\']',
                                ]
                                for pattern in img_patterns:
                                    matches = re.findall(pattern, script_text, re.IGNORECASE)
                                    if matches:
                                        for match in matches:
                                            # Filter out logos and ensure it's a valid Instagram CDN URL
                                            if (('instagram.com' in match or 'cdninstagram.com' in match or 'fbcdn.net' in match) and
                                                not any(exclude in match.lower() for exclude in ['logo', 'icon', 'brand', 'default', 'static'])):
                                                profile_pic_url = match
                                                # #region agent log
                                                debug_log(f"main.py:{310}", "Found profile_pic_url via script tag pattern", {"method": "script_pattern", "pattern": pattern, "url": profile_pic_url[:100]}, "A", "initial")
                                                # #endregion
                                                break
                                    if profile_pic_url:
                                        break
                            if profile_pic_url:
                                break
                        
                        # If still not found, search entire page text
                        if not profile_pic_url:
                            img_patterns = [
                                r'"profile_pic_url_hd":\s*"([^"]+)"',  # HD version first
                                r'"profile_pic_url":\s*"([^"]+)"',
                            ]
                            for pattern in img_patterns:
                                matches = re.findall(pattern, page_text, re.IGNORECASE)
                                if matches:
                                    for match in matches:
                                        # Filter out logos and ensure it's a valid Instagram CDN URL
                                        is_logo = any(exclude in match.lower() for exclude in ['logo', 'icon', 'brand', 'default', 'static'])
                                        is_valid_cdn = 'instagram.com' in match or 'cdninstagram.com' in match or 'fbcdn.net' in match
                                        # #region agent log
                                        debug_log(f"main.py:{328}", "Evaluating potential profile pic URL", {"match": match[:100], "is_logo": is_logo, "is_valid_cdn": is_valid_cdn, "will_use": is_valid_cdn and not is_logo}, "C", "initial")
                                        # #endregion
                                        if is_valid_cdn and not is_logo:
                                            profile_pic_url = match
                                            break
                                if profile_pic_url:
                                    break
                    
                    # Method 3: Try og:image meta tag (but filter out logos)
                    if not profile_pic_url:
                        og_image = soup.find("meta", property="og:image")
                        if og_image and og_image.get("content"):
                            img_url = og_image["content"]
                            # #region agent log
                            debug_log(f"main.py:{337}", "Found og:image", {"og_image_url": img_url[:100] if img_url else None, "is_logo": any(exclude in img_url.lower() for exclude in ['logo', 'icon', 'brand', 'static', 'default']) if img_url else False}, "B", "initial")
                            # #endregion
                            # Only use if it doesn't look like a logo
                            if not any(exclude in img_url.lower() for exclude in ['logo', 'icon', 'brand', 'static', 'default']):
                                profile_pic_url = img_url
                    
                    # Method 4: Try JSON-LD structured data (filter logos)
                    if not profile_pic_url:
                        json_scripts = soup.find_all('script', type='application/ld+json')
                        for script in json_scripts:
                            try:
                                data = json.loads(script.string)
                                if isinstance(data, dict):
                                    # Look for image in various possible locations
                                    if 'image' in data:
                                        img = data.get('image')
                                        img_url = None
                                        if isinstance(img, str):
                                            img_url = img
                                        elif isinstance(img, dict) and 'url' in img:
                                            img_url = img['url']
                                        
                                        if img_url and not any(exclude in img_url.lower() for exclude in ['logo', 'icon', 'brand', 'static', 'default']):
                                            profile_pic_url = img_url
                                            break
                            except (json.JSONDecodeError, ValueError, AttributeError):
                                continue
                    
                    # Method 5: Try to find img tag with profile picture
                    if not profile_pic_url:
                        img_tags = soup.find_all('img')
                        for img in img_tags:
                            src = img.get('src', '')
                            srcset = img.get('srcset', '')
                            # Check src and srcset
                            for img_src in [src] + (srcset.split(',') if srcset else []):
                                img_src = img_src.strip().split()[0] if img_src.strip() else img_src.strip()
                                if img_src and ('instagram.com' in img_src or 'cdninstagram.com' in img_src or 'fbcdn.net' in img_src):
                                    # Look for profile picture indicators and exclude logos
                                    alt = img.get('alt', '').lower()
                                    class_name = ' '.join(img.get('class', [])).lower()
                                    # Check if it looks like a profile picture
                                    if (('profile' in alt or 'avatar' in alt or 'user' in alt or 
                                         'profile' in class_name or 'avatar' in class_name) and
                                        not any(exclude in img_src.lower() for exclude in ['logo', 'icon', 'brand', 'static', 'default', 'glyph'])):
                                        profile_pic_url = img_src
                                        break
                            if profile_pic_url:
                                break
                    
                    # Method 6: More aggressive search - look for Instagram CDN URLs with profile picture patterns
                    if not profile_pic_url:
                        # Look for URLs that match Instagram's profile picture CDN pattern
                        # Instagram profile pics often have patterns like: s150x150, s320x320, etc.
                        profile_pic_patterns = [
                            r'https://[^"\s]+s\d+x\d+[^"\s]*\.(?:jpg|jpeg|png|webp)',  # Instagram CDN pattern with size
                            r'https://[^"\s]+/s\d+[^"\s]*\.(?:jpg|jpeg|png|webp)',
                            r'https://[^"\s]*cdninstagram\.com[^"\s]*\.(?:jpg|jpeg|png|webp)',
                            r'https://[^"\s]*fbcdn\.net[^"\s]*\.(?:jpg|jpeg|png|webp)',
                        ]
                        for pattern in profile_pic_patterns:
                            matches = re.findall(pattern, page_text)
                            if matches:
                                for match in matches:
                                    # Must be from Instagram CDN and not a logo
                                    if not any(exclude in match.lower() for exclude in ['logo', 'icon', 'brand', 'static', 'default', 'glyph', 'sprite', 'badge']):
                                        # Prefer URLs that might contain common profile picture sizes
                                        if any(size in match for size in ['/s150x150/', '/s320x320/', '/s640x640/', 's150x150', 's320x320']):
                                            profile_pic_url = match
                                            break
                                        # Or if it's the first non-logo image from Instagram CDN, use it
                                        elif not profile_pic_url:
                                            profile_pic_url = match
                                if profile_pic_url:
                                    break

                # Clean up the profile picture URL (remove escape sequences, etc.)
                if profile_pic_url:
                    # Remove common escape sequences
                    profile_pic_url = profile_pic_url.replace('\\/', '/').replace('\\u0026', '&')
                    # Remove query parameters that might cause issues (but keep if it's a size parameter)
                    if '?' in profile_pic_url and 's150x150' not in profile_pic_url and 's320x320' not in profile_pic_url:
                        base_url = profile_pic_url.split('?')[0]
                        profile_pic_url = base_url
                
                # Last resort: Try to use og:image even if it might be a logo, but verify it's actually an image
                if not profile_pic_url:
                    og_image = soup.find("meta", property="og:image")
                    if og_image and og_image.get("content"):
                        img_url = og_image["content"]
                        # Check if it's actually an image URL (not a logo)
                        if img_url.endswith(('.jpg', '.jpeg', '.png', '.webp')) or 'image' in img_url.lower():
                            # Even if it might be a logo, try it as last resort
                            profile_pic_url = img_url
                
                # #region agent log
                debug_log(f"main.py:{395}", "Profile pic extraction result", {"profile_pic_url": profile_pic_url[:150] if profile_pic_url else None, "url_length": len(profile_pic_url) if profile_pic_url else 0, "is_empty": not profile_pic_url}, "A", "initial")
                # #endregion
                
                profile_pic_src = profile_pic_url if profile_pic_url else 'https://via.placeholder.com/80?text=No+Image'
                
                # #region agent log
                debug_log(f"main.py:{400}", "Final profile_pic_src", {"profile_pic_src": profile_pic_src[:150], "is_placeholder": 'placeholder' in profile_pic_src.lower()}, "A", "initial")
                # #endregion
                if embed_images and profile_pic_url:
                    try:
                        img_response = requests.get(profile_pic_url, headers=ig_headers, timeout=10)
                        if img_response.status_code == 200:
                            content_type = img_response.headers.get('Content-Type', 'image/jpeg')
                            img_base64 = base64.b64encode(img_response.content).decode('utf-8')
                            profile_pic_src = f"data:{content_type};base64,{img_base64}"
                    except Exception:
                        pass

                result = {
                    'name': artist_name,
                    'username': username,
                    'bio': bio,
                    'followers': followers,
                    'profile_pic': profile_pic_src,
                    'link': instagram_link
                }
                # #region agent log
                debug_log(f"main.py:{362}", "Returning Instagram data", {"artist_name": artist_name, "username": username, "profile_pic_final": profile_pic_src[:100], "has_profile_pic": bool(profile_pic_url)}, "A", "initial")
                # #endregion
                return result

            except Exception as e:
                return {
                    'name': artist_name,
                    'error': f'Error fetching Instagram data - {str(e)}'
                }

        else:
            return {
                'name': artist_name,
                'error': 'Unable to locate Instagram link'
            }

    except Exception as e:
        return {
            'name': artist_name,
            'error': f'Error fetching Instagram data - {str(e)}'
        }

@app.route('/api/spotify_artists')
def api_spotify_artists():
    access_token = session.get('access_token')
    if not access_token:
        return jsonify({'error': 'Not authenticated'}), 401
    
    artists, error = get_spotify_artists(access_token)
    if error:
        return jsonify({'error': error}), 500
    
    if not artists:
        return jsonify([])
    
    # Return list of artist names and total for progress
    artist_names = [artist['name'] for artist in artists]
    return jsonify({'artists': artist_names, 'total': len(artist_names)})

@app.route('/api/instagram_data')
def api_instagram_data():
    access_token = session.get('access_token')
    if not access_token:
        return jsonify({'error': 'Not authenticated'}), 401
    
    artist_name = request.args.get('artist')
    if not artist_name:
        return jsonify({'error': 'Missing artist parameter'}), 400
    
    data = get_instagram_data(artist_name)
    return jsonify(data)

@app.route('/followed_artists')
def followed_artists():
    if not session.get('access_token'):
        return redirect(url_for('login'))
    
    return """
    <html>
    <head>
        <title>Followed Artists</title>
        <style>
            body { font-family: Arial, sans-serif; background-color: #f4f4f9; color: #333; margin: 0; padding: 20px; }
            #loading { text-align: center; padding: 50px; background: white; border-radius: 10px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); max-width: 600px; margin: 100px auto; }
            #progress-bar-container { width: 100%; background-color: #ddd; border-radius: 5px; margin-top: 20px; }
            #progress-bar { width: 0%; height: 30px; background-color: #4caf50; text-align: center; line-height: 30px; color: white; border-radius: 5px; transition: width 0.3s; }
            #content { max-width: 800px; margin: 0 auto; display: none; }
            .artist-card { background: white; border-radius: 10px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); padding: 20px; margin-bottom: 20px; display: flex; align-items: center; }
            .artist-card img { border-radius: 50%; margin-right: 20px; width: 80px; height: 80px; object-fit: cover; background-color: #e0e0e0; }
            .artist-card img[src=""] { display: none; }
            .artist-info { flex: 1; }
            .artist-info h3 { margin: 0 0 10px; color: #222; }
            .artist-info p { margin: 5px 0; font-size: 14px; }
            .follow-btn { background: #405de6; color: white; padding: 8px 16px; border: none; border-radius: 5px; cursor: pointer; text-decoration: none; }
            .follow-btn:hover { background: #3b55d1; }
            .bulk-btn, .download-btn { background: #2196f3; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; margin-right: 10px; }
            .bulk-btn:hover, .download-btn:hover { background: #1e88e5; }
            .error { color: red; }
        </style>
    </head>
    <body>
        <div id="loading">
            <h2>Loading followed artists...</h2>
            <div id="progress-bar-container">
                <div id="progress-bar">0%</div>
            </div>
        </div>
        <div id="content">
            <div id="artists-container"></div>
            <button class="bulk-btn" id="bulk-follow-btn" style="display: none;" onclick="bulkFollow()">Bulk Follow All on Instagram</button>
            <a href="/download" download="artists.html"><button class="download-btn">Download Offline HTML</button></a>
        </div>
        <script>
            let urls = [];
            let totalArtists = 0;
            let processed = 0;
            const progressBar = document.getElementById('progress-bar');

            function updateProgress() {
                const percentage = totalArtists > 0 ? Math.round((processed / totalArtists) * 100) : 0;
                progressBar.style.width = percentage + '%';
                progressBar.innerText = percentage + '%';
            }

            fetch('/api/spotify_artists')
                .then(response => {
                    if (!response.ok) throw new Error('Error fetching Spotify artists');
                    return response.json();
                })
                .then(data => {
                    if (data.artists && data.artists.length === 0) {
                        document.getElementById('loading').innerHTML = '<p>You are not following any artists.</p>';
                        return;
                    }
                    totalArtists = data.total;
                    updateProgress();
                    document.getElementById('loading').querySelector('h2').innerText = 'Fetching Instagram profiles...';

                    const container = document.getElementById('artists-container');

                    data.artists.forEach(artist => {

                        fetch(`/api/instagram_data?artist=${encodeURIComponent(artist)}`,  {
                                credentials: "same-origin"
                            })
                            .then(res => {
                                if (!res.ok) throw new Error('Error fetching Instagram data');
                                return res.json();
                            })
                            .then(artist => {

                                processed++;
                                updateProgress();

                                let html = '';

                                if (artist.error) {
                                    html = `<div class="artist-card">
                                            <div class="artist-info">
                                            <h3>${artist.name}</h3>
                                            <p class="error">${artist.error}</p>
                                            </div></div>`;
                                } else {

                                    html = `
                                    <div class="artist-card">
                                        <img src="${artist.profile_pic}" alt="${artist.name}" onerror="this.onerror=null; this.src='https://via.placeholder.com/80?text=No+Image';">
                                        <div class="artist-info">
                                            <h3>${artist.name} (@${artist.username})</h3>
                                            <p><strong>Bio:</strong> ${artist.bio}</p>
                                            <p><strong>Followers:</strong> ${artist.followers.toLocaleString()}</p>
                                            <a href="${artist.link}" target="_blank" class="follow-btn">
                                            Follow on Instagram
                                            </a>
                                        </div>
                                    </div>
                                    `;

                                    urls.push(artist.link);
                                }

                                container.innerHTML += html;

                                if (urls.length > 0) {
                                    document.getElementById('bulk-follow-btn').style.display = 'inline-block';
                                }

                                document.getElementById('content').style.display = 'block';

                                if (processed === totalArtists) {
                                    document.getElementById('loading').style.display = 'none';
                                }

                            })
                            .catch(err => {
                                processed++;
                                updateProgress();
                            });

                    });

                })
                .catch(error => {
                    document.getElementById('loading').innerHTML = '<p class="error">Error: ' + error.message + '</p>';
                });

            // Bulk follow function
            function bulkFollow() {
                function openNext(index) {
                    if (index >= urls.length) return;
                    window.open(urls[index], '_blank');
                    setTimeout(() => openNext(index + 1), 5000);
                }
                openNext(0);
            }
        </script>
    </body>
    </html>
    """

@app.route('/download')
def download():
    access_token = session.get('access_token')
    if not access_token:
        return redirect(url_for('login'))
    
    artists, error = get_spotify_artists(access_token)
    if error:
        return error, 500
    
    data = []
    if artists:
        artist_names = [artist['name'] for artist in artists]
        for name in artist_names:
            artist_data = get_instagram_data(name, embed_images=True)
            data.append(artist_data)
    
    profiles_html = ''
    instagram_urls = []
    if not data:
        profiles_html = '<p>You are not following any artists.</p>'
    else:
        for artist in data:
            if 'error' in artist:
                profiles_html += f"<p>{artist['name']}: {artist['error']}</p>"
            else:
                profiles_html += f"""
                <div style="border: 1px solid #ddd; padding: 10px; margin-bottom: 20px;">
                    <h3>{artist['name']} (@{artist['username']})</h3>
                    <img src="{artist['profile_pic']}" alt="Profile Picture" style="width: 100px; height: 100px; border-radius: 50%;">
                    <p><strong>Bio:</strong> {artist['bio']}</p>
                    <p><strong>Followers:</strong> {artist['followers']}</p>
                    <a href="{artist['link']}" target="_blank">Follow on Instagram</a>
                </div>
                """
                instagram_urls.append(artist['link'])
    
    bulk_js = """
    <script>
    function bulkFollow() {
        const urls = %s;
        function openNext(index) {
            if (index >= urls.length) return;
            window.open(urls[index], '_blank');
            setTimeout(() => openNext(index + 1), 5000);
        }
        openNext(0);
    }
    </script>
    """ % json.dumps(instagram_urls)
    
    bulk_button = '<button onclick="bulkFollow()">Bulk Follow All on Instagram</button><br><br>'
    
    full_html = f"""
    <html>
    <head>
        <title>Followed Artists Instagram Profiles</title>
    </head>
    <body>
        {bulk_button}
        {profiles_html}
        {bulk_js}
    </body>
    </html>
    """
    
    return Response(full_html, mimetype='text/html', headers={'Content-Disposition': 'attachment; filename=artists.html'})

if __name__ == '__main__':
    app.run(debug=True)