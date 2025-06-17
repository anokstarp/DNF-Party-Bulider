#!/usr/bin/env python3
import sys
import os
import re
from urllib.parse import quote
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# 설정
BASE_URL        = 'https://dundam.xyz/search'
FIXED_SERVER    = 'adven'
USER_AGENT      = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
GOTO_TIMEOUT    = 60000
SELECTOR_TIMEOUT= 60000

def scrape_detail_urls(page, user_name: str):
    """
    주어진 user_name 으로 검색 페이지에 접속해
    각 캐릭터의 (server, char_id) 튜플을 출력한다.
    """
    url = f"{BASE_URL}?server={FIXED_SERVER}&name={quote(user_name)}"
    try:
        page.goto(url, wait_until='domcontentloaded', timeout=GOTO_TIMEOUT)
        page.wait_for_selector('div.scon', timeout=SELECTOR_TIMEOUT)
    except PlaywrightTimeoutError:
        return

    for scon in page.query_selector_all('div.scon'):
        img_el = scon.query_selector('div.seh_abata div.imgt img')
        src = img_el.get_attribute('src') if img_el else None
        if not src:
            continue
        # 절대 URL 보정
        if src.startswith('/'):
            src = 'https://dundam.xyz' + src
        m = re.search(r'/servers/([^/]+)/characters/([^?]+)', src)
        if m:
            server, char_id = m.group(1), m.group(2)
            # 표준출력에 튜플 문자열로 찍음
            print((server, char_id))

def main(user_names):
    # Playwright 브라우저 세팅
    playwright = sync_playwright().start()
    browser    = playwright.chromium.launch(headless=True)
    ctx        = browser.new_context(user_agent=USER_AGENT)
    page       = ctx.new_page()
    # 불필요한 리소스 차단 (이미지, CSS 등)
    page.route("**/*.{png,jpg,jpeg,svg,gif,css,woff,woff2,ttf}", lambda r: r.abort())

    # 각 유저 이름에 대해 튜플 출력
    for name in user_names:
        scrape_detail_urls(page, name)

    # 정리
    page.close()
    ctx.close()
    browser.close()
    playwright.stop()

if __name__ == '__main__':
    # sys.argv[1:] 에 유저 이름(들)이 들어온다
    users = sys.argv[1:]
    if not users:
        print("Usage: python scrap_char.py [UserName1] [UserName2] ...", file=sys.stderr)
        sys.exit(1)
    main(users)
