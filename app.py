from flask import Flask, session, redirect, request, url_for, render_template
import requests
from scrape_music_from_yt import scrape_music_panel_with_bs
from functools import wraps

import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv
import os

load_dotenv(override=True)

def spotify_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'spotify_token' not in session:
            # Redirect to Spotify's authorization page
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

app = Flask(__name__)
app.secret_key = os.urandom(24)  # For session encryption
app.config['SESSION_COOKIE_NAME'] = 'playlister_session'

sp_oauth = SpotifyOAuth(
    scope="playlist-modify-public playlist-modify-private",
    redirect_uri=os.getenv("SPOTIPY_REDIRECT_URI"),
    client_id=os.getenv("SPOTIPY_CLIENT_ID"),
    client_secret=os.getenv("SPOTIPY_CLIENT_SECRET"),
    cache_path=".cache"
)

@app.route('/')
def index():
    if 'spotify_token' in session:
        playlists = get_user_playlists()
        return render_template('index.html', playlists=playlists)
    else:
        print("REDIRECT URI:", sp_oauth.redirect_uri)
        auth_url = sp_oauth.get_authorize_url()
        return redirect(auth_url)

@app.route('/callback')
def callback():
    code = request.args.get('code')
    token_info = sp_oauth.get_access_token(code)
    session['spotify_token'] = token_info
    return redirect(url_for('index'))

@app.route('/logout')
@spotify_login_required
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/analyze', methods=['GET', 'POST'])
@spotify_login_required
def analyze():
    if request.method == 'POST':
        youtube_url = request.form.get('youtube_url')
        if youtube_url:
            results = scrape_music_panel_with_bs(youtube_url)
            return render_template('analyze.html', results=results, youtube_url=youtube_url)
        else:
            error = "Please provide a YouTube URL."
            return render_template('analyze.html', error=error)
    return render_template('analyze.html')

def get_user_playlists():
    access_token = session.get('spotify_token')
    if not access_token:
        return []

    _access_token = access_token.get("access_token")
    headers = {
        'Authorization': f'Bearer {_access_token}'
    }
    playlists = []
    url = 'https://api.spotify.com/v1/me/playlists'
    while url:
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            break
        data = response.json()
        playlists.extend(data.get('items', []))
        url = data.get('next')  # Pagination
    return playlists

if __name__ == '__main__':
    app.run(debug=True)
