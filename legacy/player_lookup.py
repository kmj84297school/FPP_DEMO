# player_lookup.py
import time, re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup

SEARCH_URL = "https://fbref.com/search/search.fcgi?search="

def init_driver(headless=True):
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36")
    return webdriver.Chrome(options=options)

def get_player_id(name, driver, delay=2):
    try:
        driver.get(SEARCH_URL + name.replace(" ", "+"))
        time.sleep(delay)
        soup = BeautifulSoup(driver.page_source, "lxml")
        for a in soup.select("a[href]"):
            href = a.get("href", "")
            if re.match(r"^/en/players/[0-9a-f]{8}/", href):
                m = re.match(r"^/en/players/([0-9a-f]{8})/", href)
                if m:
                    return m.group(1)
    except Exception as e:
        print("❌ Error:", name, e)
    return None
