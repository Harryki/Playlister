import time
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from typing import List, Optional

class TrackMetadata:
    def __init__(self, title: str, artist: Optional[str] = None, album: Optional[str] = None) -> None:
        self.title: str = title
        self.artist: Optional[str] = artist
        self.album: Optional[str] = album

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "artist": self.artist,
            "album": self.album
        }

    def __eq__(self, other) -> bool:
        if not isinstance(other, TrackMetadata):
            return False
        return (
            self.title == other.title and
            self.artist == other.artist and
            self.album == other.album
        )

    def __hash__(self) -> int:
        return hash((self.title, self.artist, self.album))

    def __str__(self):
        return f"TrackMetadata(title={self.title}, artist={self.artist}, album={self.album})"

class YouTubeMusicMetadata:
    def __init__(self, video_title: str, tracks: List[TrackMetadata]) -> None:
        self.video_title: str = video_title
        self.tracks: List[TrackMetadata] = tracks

    def to_dict(self) -> dict:
        return {
            "video_title": self.video_title,
            "tracks": [track.to_dict() for track in self.tracks]
        }
    def __str__(self):
        return f"YouTubeMusicMetadata(video_title={self.video_title}, tracks={self.tracks})"


def scrape_music_panel_with_playwright(youtube_url: str) -> YouTubeMusicMetadata:
    start = time.perf_counter()
    print(f"[INFO] Starting scrape for: {youtube_url}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        t1 = time.perf_counter()
        print("[INFO] Navigating to YouTube URL...")
        page.goto(youtube_url, wait_until="networkidle")
        print(f"[INFO] Page loaded in {time.perf_counter() - t1:.2f} seconds.")

        t2 = time.perf_counter()
        print("[INFO] Waiting for music panel...")
        page.wait_for_selector("yt-video-attribute-view-model", timeout=10000, state="attached")
        print(f"[INFO] Music panel appeared in {time.perf_counter() - t2:.2f} seconds.")

        content = page.content()
        browser.close()

    soup = BeautifulSoup(content, "html.parser")
    video_title_tag = soup.find("title")
    video_title: str = video_title_tag.text.replace("- YouTube", "").strip() if video_title_tag else "Unknown Title"
    print(f"[INFO] Video title: {video_title}")

    tracks: List[TrackMetadata] = []

    for card in soup.find_all("yt-video-attribute-view-model"):
        try:
            inner_soup = BeautifulSoup(str(card), "html.parser")

            title_el = inner_soup.select_one(".yt-video-attribute-view-model__title")
            artist_el = inner_soup.select_one(".yt-video-attribute-view-model__subtitle span")
            album_el = inner_soup.select_one(".yt-video-attribute-view-model__secondary-subtitle span")

            title: Optional[str] = title_el.text.strip() if title_el else None
            artist: Optional[str] = artist_el.text.strip() if artist_el else None
            album: Optional[str] = album_el.text.strip() if album_el else None

            if title and artist and album:
                track = TrackMetadata(title, artist, album)
                if track not in tracks:
                    tracks.append(track)
                    print(f"[TRACK] Title: {title}, Artist: {artist}, Album: {album}")

        except Exception as e:
            print(f"[WARN] Skipped a card due to: {e}")

    print(f"[INFO] Found {len(tracks)} tracks.")
    print(f"[INFO] Total scrape duration: {time.perf_counter() - start:.2f} seconds.")
    return YouTubeMusicMetadata(video_title, tracks)

# def extract_chapters_as_metadata(youtube_url: str) -> YouTubeMusicMetadata:
#     """
#     Extracts chapter metadata from a YouTube video using yt-dlp.
#     Returns a YouTubeMusicMetadata object with track titles from chapters.
#     """
#     ydl_opts = {
#         'quiet': True,
#         'no_warnings': True,
#         'skip_download': True,
#     }

#     with yt_dlp.YoutubeDL(ydl_opts) as ydl:
#         info = ydl.extract_info(youtube_url, download=False)

#         video_title = info.get("title", "Unknown Title")
#         chapters = info.get("chapters", [])

#         tracks = []
#         for chapter in chapters:
#             title = chapter.get("title", "").strip()
#             if title:
#                 track = TrackMetadata(title=title)
#                 if track not in tracks:
#                     tracks.append(track)

#         return YouTubeMusicMetadata(video_title, tracks)
