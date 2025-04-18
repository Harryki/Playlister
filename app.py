from flask import Flask, session, redirect, request, url_for, render_template
from scrape_music_from_yt import scrape_music_panel_with_bs

import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv
import os

load_dotenv(override=True)

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
    if 'token_info' in session:
        return render_template("index.html")
    else:
        print("REDIRECT URI:", sp_oauth.redirect_uri)
        auth_url = sp_oauth.get_authorize_url()
        return redirect(auth_url)

@app.route('/callback')
def callback():
    code = request.args.get('code')
    token_info = sp_oauth.get_access_token(code)
    session['token_info'] = token_info
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/analyze', methods=['GET', 'POST'])
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

if __name__ == '__main__':
    app.run(debug=True)
