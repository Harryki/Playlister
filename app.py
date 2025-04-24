from datetime import timedelta
import sys
import time
import requests
import logging
import os
import base64
import redis

from flask import Flask, current_app, session, redirect, request, url_for, render_template
from flask_session import Session
from dotenv import load_dotenv
from views.analyze import analyze_bp

load_dotenv(override=True)

redis_host = os.environ.get("REDIS_HOST", "localhost")

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.urandom(24)
r = redis.from_url(f"redis://{redis_host}:6379")

# Redis-backed sessions
app.config.update(
    SESSION_TYPE="redis",
    SESSION_REDIS=r,
    SESSION_USE_SIGNER=True,
    SESSION_KEY_PREFIX="playlister:",
    SESSION_COOKIE_NAME="playlister_session",
    SESSION_COOKIE_SAMESITE="None",
    SESSION_COOKIE_SECURE=os.environ.get("FLASK_SECURE_COOKIE", "false").lower() == "true",
    SESSION_PERMANENT=True,
    PERMANENT_SESSION_LIFETIME=timedelta(hours=1),
    TEMPLATES_AUTO_RELOAD=True,
)

Session(app)

formatter = logging.Formatter("[%(asctime)s] %(levelname)s in %(module)s: %(message)s")
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(formatter)
stream_handler.setLevel(logging.DEBUG)

if not app.debug and not app.testing:
    app.logger.handlers.clear()
    app.logger.setLevel(logging.DEBUG)
    app.logger.addHandler(stream_handler)
    app.logger.propagate = False

    scrape_logger = logging.getLogger("scrape")
    scrape_logger.handlers = app.logger.handlers
    scrape_logger.setLevel(app.logger.level)
    scrape_logger.propagate = False

required_vars = ["SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET", "SPOTIFY_REDIRECT_URI"]
for var in required_vars:
    if not os.getenv(var):
        raise RuntimeError(f"Missing required env var: {var}")

def get_spotify_token(code):
    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI")

    auth_header = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    headers = {
        "Authorization": f"Basic {auth_header}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri
    }
    response = requests.post("https://accounts.spotify.com/api/token", headers=headers, data=data)
    response.raise_for_status()
    return response.json()

def get_user_profile(access_token):
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get("https://api.spotify.com/v1/me", headers=headers)
    response.raise_for_status()
    return response.json()

def get_user_playlists(headers):
    response = requests.get('https://api.spotify.com/v1/me/playlists', headers=headers)
    if response.status_code != 200:
        app.logger.error(f"Failed to fetch playlists: {response.text}")
        return []
    return response.json().get('items', [])

@app.before_request
def log_cookie_info():
    app.logger.debug(f"[session] keys: {list(session.keys())}")
    app.logger.debug(f"[session] spotify_token: {session.get('spotify_token')}")
    app.logger.debug(f"[session] sid: {request.cookies.get('playlister_session')}")

@app.route('/')
def index():
    if 'spotify_token' in session:
        token_info = session['spotify_token']
        access_token = token_info['access_token']

        headers = {"Authorization": f"Bearer {access_token}"}
        start = time.time()
        playlists = get_user_playlists(headers)
        app.logger.info(f"[index] Spotify playlist fetch took {time.time() - start:.2f}s")

        spotify_user = session.get('spotify_user', {})
        user_info = {
            'id': spotify_user.get('id', 'unknown'),
            'display_name': spotify_user.get('display_name', 'Guest'),
            'images': spotify_user.get('images', []),
            'followers': spotify_user.get('followers', {'total': 0})
        }
        return render_template('index.html', playlists=playlists, user=user_info)
    else:
        app.logger.info("[index] No Spotify token found, redirecting to login")
        client_id = os.getenv("SPOTIFY_CLIENT_ID")
        redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI")
        scope = "playlist-modify-public playlist-modify-private"
        auth_url = (
            f"https://accounts.spotify.com/authorize?client_id={client_id}"
            f"&response_type=code&redirect_uri={redirect_uri}&scope={scope}&show_dialog=true"
        )
        app.logger.debug(f"[index] auth_url: {auth_url}")
        return redirect(auth_url)

@app.route('/callback')
def callback():
    code = request.args.get('code')
    if not code:
        app.logger.warning("[CALLBACK] No authorization code received.")
        return redirect(url_for('index'))

    try:
        token_info = get_spotify_token(code)
        session['spotify_token'] = token_info
        session.permanent = True
        access_token = token_info['access_token']

        user_info = get_user_profile(access_token)
        session['spotify_user'] = {
            'id': user_info['id'],
            'display_name': user_info['display_name'],
            'images': user_info['images'],
            'followers': user_info.get('followers', {})
        }

        app.logger.info(f"[CALLBACK] Logged in as user: {user_info['id']}")
        app.logger.debug(f"[CALLBACK] Display name: {user_info.get('display_name')}")
        app.logger.debug(f"[CALLBACK] followers : {user_info.get('followers', {}).get('total', 0)}")
        app.logger.debug(f"[CALLBACK] Profile image count: {len(user_info.get('images', []))}")

        if user_info.get('images'):
            app.logger.debug(f"[CALLBACK] First profile image URL: {user_info['images'][0].get('url')}")
    except Exception as e:
        app.logger.error(f"[CALLBACK] Error during Spotify auth or profile fetch: {e}")

    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session_id = request.cookies.get(current_app.config["SESSION_COOKIE_NAME"])
    user_id = session.get('spotify_user') or 'Unknown'
    app.logger.info(f"[LOGOUT] Logging out user: {user_id}")

    token = session.get('spotify_token', {}).get('access_token')
    if token:
        app.logger.debug(f"[LOGOUT] Clearing access token: {token[:10]}...")

    session.clear()

    if session_id:
        redis_key = f"{current_app.config['SESSION_KEY_PREFIX']}{session_id}"
        r.delete(redis_key)

    app.logger.info("[LOGOUT] Session cleared.")
    return redirect("https://accounts.spotify.com/en/logout")

@app.route("/logtest")
def logtest():
    app.logger.info("📢 INFO from /logtest")
    app.logger.debug("🛠️ DEBUG from /logtest")
    return "Log test route hit!", 200

app.register_blueprint(analyze_bp)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
