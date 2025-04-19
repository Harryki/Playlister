from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from typing import List, Optional

class TrackMetadata:
    def __init__(self, title: str, artist: str, album: str) -> None:
        self.title: str = title
        self.artist: str = artist
        self.album: str = album

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

class YouTubeMusicMetadata:
    def __init__(self, video_title: str, tracks: List[TrackMetadata]) -> None:
        self.video_title: str = video_title
        self.tracks: List[TrackMetadata] = tracks

    def to_dict(self) -> dict:
        return {
            "video_title": self.video_title,
            "tracks": [track.to_dict() for track in self.tracks]
        }


def scrape_music_panel_with_bs(youtube_url: str) -> YouTubeMusicMetadata:
    options: Options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")

    driver: webdriver.Chrome = webdriver.Chrome(options=options)
    driver.get(youtube_url)

    # 🚀 Wait for the music panel to show up
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.TAG_NAME, "yt-video-attribute-view-model"))
    )

    # Get the video title
    video_title: str = driver.title.replace("- YouTube", "").strip()

    cards = driver.find_elements(By.TAG_NAME, "yt-video-attribute-view-model")
    tracks: List[TrackMetadata] = []

    for card in cards:
        try:
            inner_html: Optional[str] = card.get_attribute("innerHTML")
            if not inner_html:
                continue
            soup: BeautifulSoup = BeautifulSoup(inner_html, "html.parser")

            title_el = soup.select_one(".yt-video-attribute-view-model__title")
            artist_el = soup.select_one(".yt-video-attribute-view-model__subtitle span")
            album_el = soup.select_one(".yt-video-attribute-view-model__secondary-subtitle span")

            title: Optional[str] = title_el.text.strip() if title_el else None
            artist: Optional[str] = artist_el.text.strip() if artist_el else None
            album: Optional[str] = album_el.text.strip() if album_el else None

            track = TrackMetadata(title, artist, album)
            if title and artist and album and track not in tracks:
                tracks.append(track)

        except Exception as e:
            print(f"Skipped a card due to: {e}")

    driver.quit()
    return YouTubeMusicMetadata(video_title, tracks)

# 🔍 Example usage:
# url = "https://www.youtube.com/watch?v=goZ6lwE2ZmU"
# # url = "https://www.youtube.com/watch?v=ksQ5k9e-1_U"
# tracks = scrape_music_panel_with_bs(url)

# for t in tracks:
#     print(f"{t['title']} – {t['artist']} ({t['album']})")
