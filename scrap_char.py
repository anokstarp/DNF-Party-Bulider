from urllib.parse import quote
import re
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# 설정
BASE_URL = 'https://dundam.xyz/search'
FIXED_SERVER = 'adven'
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
GOTO_TIMEOUT = 60000
SELECTOR_TIMEOUT = 60000
GROUP_FILE = 'character.txt'

# 사용자 파일에서 이름 목록 로드

def load_users(path):
    users = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '(' in line and line.endswith(')'):
                user = line.split('(', 1)[0]
            else:
                user = line
            users.append(user.strip())
    return users

# Playwright 브라우저 초기화

playwright = sync_playwright().start()
browser = playwright.chromium.launch(headless=True)
ctx = browser.new_context(user_agent=USER_AGENT)
page = ctx.new_page()
# 이미지/스타일 리소스 차단
page.route("**/*.{png,jpg,jpeg,svg,gif,css,woff,woff2,ttf}", lambda r: r.abort())

# 단일 사용자로부터 캐릭터 상세 URL 생성 및 출력

def scrape_detail_urls(user_name: str):
    url = f"{BASE_URL}?server={FIXED_SERVER}&name={quote(user_name)}"
    try:
        page.goto(url, wait_until='domcontentloaded', timeout=GOTO_TIMEOUT)
        page.wait_for_selector('div.scon', timeout=SELECTOR_TIMEOUT)
    except PlaywrightTimeoutError:
        return

    for scon in page.query_selector_all('div.scon'):
        img_el = scon.query_selector('div.seh_abata div.imgt img')
        img_src = img_el.get_attribute('src') if img_el else None
        if not img_src:
            continue
        if img_src.startswith('/'):
            img_src = f"https://dundam.xyz{img_src}"
        m = re.search(r'/servers/([^/]+)/characters/([^?]+)', img_src)
        if m:
            server, char_id = m.group(1), m.group(2)
            # URL 대신 튜플로 출력
            print((server, char_id))

if __name__ == '__main__':
    users = load_users(GROUP_FILE)
    for user in users:
        scrape_detail_urls(user)
    # 브라우저 정리
    page.close()
    ctx.close()
    browser.close()
    playwright.stop()
