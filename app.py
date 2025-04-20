from flask import Flask, abort, flash, session, redirect, request, url_for, render_template
import requests
from scrape_music_from_yt import scrape_music_panel_with_bs
from functools import wraps
import logging
from logging.handlers import RotatingFileHandler

from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv
import os

load_dotenv(override=True)

if not os.path.exists('logs'):
    os.mkdir('logs')

file_handler = RotatingFileHandler('logs/playlister.log', maxBytes=10240, backupCount=10)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
file_handler.setLevel(logging.INFO)

def spotify_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'spotify_token' not in session:
            # Redirect to Spotify's authorization page
            return redirect(url_for('index', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

app = Flask(__name__)
app.secret_key = os.urandom(24)  # For session encryption
app.config['SESSION_COOKIE_NAME'] = 'playlister_session'
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.logger.addHandler(file_handler)
app.logger.setLevel(logging.INFO)
app.logger.info('Playlister startup')

sp_oauth = SpotifyOAuth(
    scope="playlist-modify-public playlist-modify-private",
    redirect_uri=os.getenv("SPOTIPY_REDIRECT_URI"),
    client_id=os.getenv("SPOTIPY_CLIENT_ID"),
    client_secret=os.getenv("SPOTIPY_CLIENT_SECRET"),
    cache_path=".cache"
)
# @app.errorhandler(400)
# def bad_request(error):
#     return render_template('400.html', message=error.description), 400

# @app.errorhandler(404)
# def not_found_error(error):
#     app.logger.warning(f"404 error: {error}")
#     return render_template('404.html'), 404

# @app.errorhandler(500)
# def internal_error(error):
#     app.logger.error(f"500 error: {error}")
#     return render_template('500.html'), 500

@app.route('/')
def index():
    if 'spotify_token' in session:
        playlists = get_user_playlists()

        # ✅ Get user profile info
        access_token = session.get('spotify_token').get("access_token")
        headers = {
            "Authorization": f"Bearer {access_token}"
        }
        user_response = requests.get('https://api.spotify.com/v1/me', headers=headers)

        if user_response.status_code != 200:
            app.logger.error(f"Failed to fetch user info: {user_response.text}")
            user_info = None
        else:
            user_info = user_response.json()

        return render_template('index.html', playlists=playlists, user=user_info)
    else:
        auth_url = sp_oauth.get_authorize_url()
        return redirect(auth_url)

@app.route('/callback')
def callback():
    code = request.args.get('code')
    token_info = sp_oauth.get_access_token(code)
    session['spotify_token'] = token_info
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

@app.route('/analyze', methods=['GET', 'POST'])
@spotify_login_required
def analyze():
    try:
        if request.method == 'POST':
            if 'youtube_url' in request.form:
                # Step 1: Analyze YouTube URL
                youtube_url = request.form['youtube_url']
                metadata = scrape_music_panel_with_bs(youtube_url)
                # TODO: there's problem that chapter title is not always the song title. 
                # meta2 = extract_chapters_as_metadata(youtube_url)
                # compare the length of .tracks and use longer one
                # metadata = None
                # if len(meta.tracks) > len(meta2.tracks):
                #     metadata = meta
                # else:
                #     metadata = meta2
                if not metadata:
                    flash('No metadata found for the provided YouTube URL.', 'error')
                    return redirect(url_for('index'))
                
                return render_template('analyze.html', metadata=metadata)
            else:
                app.logger.info('Create Playlist Started')
                # Step 2: Create Spotify Playlist
                playlist_name = request.form.get('playlist_name', 'New Playlist')
                if not playlist_name:
                    playlist_name = 'New Playlist'

                titles = request.form.getlist('title')
                artists = request.form.getlist('artist')
                track_uris = []

                access_token = session.get('spotify_token')
                access_token = access_token.get("access_token")
                if not access_token:
                    flash('Spotify authentication required.', 'error')
                    return redirect(url_for('login'))  # Implement a login route

                headers = {'Authorization': f'Bearer {access_token}'}

                app.logger.info('Fetch Song from Spotify started')
                for title, artist in zip(titles, artists):
                    if artist:
                        query = f'track:{title} artist:{artist}'
                    else:
                        query = f'track:{title}'

                    response = requests.get(
                        'https://api.spotify.com/v1/search',
                        headers=headers,
                        params={'q': query, 'type': 'track', 'limit': 1}
                    )

                    if response.status_code != 200:
                        app.logger.error(f"Spotify search API error: {response.status_code} - {response.text}")
                        continue

                    results = response.json()
                    tracks = results.get('tracks', {}).get('items', [])
                    if tracks:
                        track_uris.append(tracks[0]['uri'])
                    else:
                        app.logger.info(f"No tracks found for query: {query}")
                app.logger.info('Fetch Song from Spotify Completed')

                # Create playlist
                user_response = requests.get('https://api.spotify.com/v1/me', headers=headers)
                if user_response.status_code != 200:
                    app.logger.error(f"Spotify user API error: {user_response.status_code} - {user_response.text}")
                    flash('Failed to retrieve Spotify user information.', 'error')
                    return redirect(url_for('index'))

                user_id = user_response.json()['id']
                playlist_response = requests.post(
                    f'https://api.spotify.com/v1/users/{user_id}/playlists',
                    headers=headers,
                    json={'name': playlist_name, 'public': True}
                )
                if playlist_response.status_code != 201:
                    app.logger.error(f"Spotify playlist creation error: {playlist_response.status_code} - {playlist_response.text}")
                    flash('Failed to create Spotify playlist.', 'error')
                    return redirect(url_for('index'))

                playlist_id = playlist_response.json()['id']

                # Add tracks to playlist
                if track_uris:
                    add_tracks_response = requests.post(
                        f'https://api.spotify.com/v1/playlists/{playlist_id}/tracks',
                        headers=headers,
                        json={'uris': track_uris}
                    )
                    if add_tracks_response.status_code != 201:
                        app.logger.error(f"Spotify add tracks error: {add_tracks_response.status_code} - {add_tracks_response.text}")
                        flash('Failed to add tracks to Spotify playlist.', 'error')
                        return redirect(url_for('index'))

                flash('Spotify playlist created successfully!', 'success')
                app.logger.info('Create Playlist Completed')
                return redirect(url_for('index'))

        return render_template('analyze.html')
    except Exception as e:
        app.logger.exception("An unexpected error occurred in the /analyze route.")
        flash('An unexpected error occurred. Please try again later.', 'error')
        return redirect(url_for('index'))

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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
