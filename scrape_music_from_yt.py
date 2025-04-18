from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time

def scrape_music_panel_with_bs(youtube_url):
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")

    driver = webdriver.Chrome(options=options)
    driver.get(youtube_url)

    # 🚀 Wait until at least one music block loads
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.TAG_NAME, "yt-video-attribute-view-model"))
    )

    cards = driver.find_elements(By.TAG_NAME, "yt-video-attribute-view-model")

    results = []

    for card in cards:
        try:
            inner_html = card.get_attribute("innerHTML")
            soup = BeautifulSoup(inner_html, "html.parser")

            title_el = soup.select_one(".yt-video-attribute-view-model__title")
            artist_el = soup.select_one(".yt-video-attribute-view-model__subtitle span")
            album_el = soup.select_one(".yt-video-attribute-view-model__secondary-subtitle span")

            title = title_el.text.strip() if title_el else None
            artist = artist_el.text.strip() if artist_el else None
            album = album_el.text.strip() if album_el else None

            if title and artist and album:
                results.append({
                    "title": title,
                    "artist": artist,
                    "album": album
                })
        except Exception as e:
            print(f"Skipped a card due to: {e}")

    driver.quit()
    return results

# 🔍 Example usage:
url = "https://www.youtube.com/watch?v=goZ6lwE2ZmU"
# url = "https://www.youtube.com/watch?v=ksQ5k9e-1_U"
tracks = scrape_music_panel_with_bs(url)

for t in tracks:
    print(f"{t['title']} – {t['artist']} ({t['album']})")
