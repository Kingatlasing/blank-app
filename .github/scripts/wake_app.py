"""Open the Streamlit app like a visitor (keeps it from sleeping) and click 'wake up' if it is asleep, then wait
until its API answers."""
import time
import requests
from playwright.sync_api import sync_playwright

APP = "https://mobilecards.streamlit.app/"
API = APP + "~/+/api/health"


def api_ok() -> bool:
    try:
        r = requests.get(API, timeout=20)
        return r.ok and r.headers.get("content-type", "").startswith("application/json")
    except Exception:
        return False


with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page()
    pg.goto(APP, timeout=90000)
    for _ in range(40):
        btn = pg.get_by_role("button", name="get this app back up", exact=False)
        if btn.count():
            print("app asleep: waking it")
            btn.first.click()
        if api_ok():
            break
        time.sleep(10)
    pg.wait_for_timeout(15000)  # stay a moment so it counts as a visit
    b.close()
print("api ok" if api_ok() else "api NOT answering")
