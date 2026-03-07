from flask import Flask, request, redirect, session, url_for
import requests
import base64
import os
from urllib.parse import urlencode
from dotenv import load_dotenv

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
        'show_dialog': 'true'  # Optional: Forces the auth dialog
    }
    auth_query = urlencode(params)
    return redirect(f'{AUTH_URL}?{auth_query}')

@app.route('/callback')
def callback():
    code = request.args.get('code')
    if not code:
        return 'Error: No code provided', 400

    # Request access token
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
    
    return redirect(url_for('get_followed_artists'))

@app.route('/followed_artists')
def get_followed_artists():
    access_token = session.get('access_token')
    if not access_token:
        return redirect(url_for('login'))
    
    headers = {
        'Authorization': f'Bearer {access_token}'
    }
    
    all_artists = []
    next_url = f'{FOLLOWED_ARTISTS_URL}?type=artist&limit=50'  # Start with the initial URL
    
    while next_url:
        response = requests.get(next_url, headers=headers)
        
        if response.status_code != 200:
            return f'Error fetching followed artists: {response.text}', response.status_code
        
        data = response.json()
        artists = data['artists']['items']
        all_artists.extend(artists)
        
        next_url = data['artists'].get('next')  # Get the next page URL if available
    
    if not all_artists:
        return 'You are not following any artists.'
    
    artist_names = [artist['name'] for artist in all_artists]
    return '<br>'.join(artist_names)

if __name__ == '__main__':
    app.run(debug=True)