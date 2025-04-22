import sys
import time
import concurrent
import requests
import logging
import os

from logging.handlers import RotatingFileHandler
from flask import Flask, session, redirect, request, url_for, render_template
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv
from views.analyze import analyze_bp

load_dotenv(override=True)

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.urandom(24)  # For session encryption
app.config['SESSION_COOKIE_NAME'] = 'playlister_session'
app.config['TEMPLATES_AUTO_RELOAD'] = True

# Ensure log directory exists
os.makedirs('logs', exist_ok=True)

formatter = logging.Formatter("[%(asctime)s] %(levelname)s in %(module)s: %(message)s")

# File handler
file_handler = RotatingFileHandler(
    "logs/playlister.log",
    maxBytes=10240,
    backupCount=10
)
file_handler.setFormatter(formatter)
file_handler.setLevel(logging.DEBUG)

# Stream handler for Docker logs
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(formatter)
stream_handler.setLevel(logging.DEBUG)

if not app.debug and not app.testing:
    # Clear existing handlers to avoid duplicates across workers
    app.logger.handlers.clear()
    app.logger.setLevel(logging.DEBUG)
    app.logger.addHandler(file_handler)
    app.logger.addHandler(stream_handler)
    app.logger.propagate = False

    # 🔥 Inherit same handlers in other modules (like scrape)
    scrape_logger = logging.getLogger("scrape")
    scrape_logger.handlers = app.logger.handlers
    scrape_logger.setLevel(app.logger.level)
    scrape_logger.propagate = False

sp_oauth = SpotifyOAuth(
    scope="playlist-modify-public playlist-modify-private",
    redirect_uri=os.getenv("SPOTIPY_REDIRECT_URI"),
    client_id=os.getenv("SPOTIPY_CLIENT_ID"),
    client_secret=os.getenv("SPOTIPY_CLIENT_SECRET"),
    cache_path=".cache",
    show_dialog=True
)

app.register_blueprint(analyze_bp)

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

def get_user_info(headers):
    response = requests.get('https://api.spotify.com/v1/me', headers=headers)
    if response.status_code != 200:
        app.logger.error(f"Failed to fetch user info: {response.text}")
        return None
    return response.json()

def get_user_playlists(headers):
    response = requests.get('https://api.spotify.com/v1/me/playlists', headers=headers)
    if response.status_code != 200:
        app.logger.error(f"Failed to fetch playlists: {response.text}")
        return []
    return response.json().get('items', [])

@app.route('/')
def index():
    if 'spotify_token' in session:
        access_token = session['spotify_token']['access_token']
        headers = {
            "Authorization": f"Bearer {access_token}"
        }

        start = time.time()

        with concurrent.futures.ThreadPoolExecutor() as executor:
            user_future = executor.submit(get_user_info, headers)
            playlists_future = executor.submit(get_user_playlists, headers)

            user_info = user_future.result()
            playlists = playlists_future.result()

        app.logger.info(f"[index] parallel Spotify calls took {time.time() - start:.2f}s")

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

@app.route("/logtest")
def logtest():
    app.logger.info("📢 INFO from /logtest")
    app.logger.debug("🐛 DEBUG from /logtest")
    return "Log test route hit!", 200

@app.route('/logout')
def logout():
    session.clear()
    return redirect("https://accounts.spotify.com/en/logout")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
