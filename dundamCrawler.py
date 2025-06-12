import json
from urllib.parse import quote
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# ── 설정 파일 ─────────────────────────────────────────────
GROUP_FILE = 'character.txt'  # 각 줄: "UserName(Label)"

BASE_URL = 'https://dundam.xyz/search'
FIXED_SERVER = 'adven'
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
GOTO_TIMEOUT = 60000
SELECTOR_TIMEOUT = 60000

# ── 그룹 파일 읽기 ─────────────────────────────────────────
def load_groups(path):
    groups = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '(' in line and line.endswith(')'):
                user, lbl = line.split('(', 1)
                lbl = lbl[:-1]
            else:
                user, lbl = line, line
            groups.append((user, lbl))
    return groups

# ── 숫자 변환 ────────────────────────────────────────────────
def parse_int(val):
    try:
        return int(val)
    except:
        return 0

# ── 버프 점수 변환 ───────────────────────────────────────────
def parse_buff(val):
    val_clean = val.replace(',', '').replace(' ', '')
    try:
        return int(val_clean)
    except ValueError:
        try:
            return float(val_clean)
        except ValueError:
            return 0

# ── 스크래퍼 ─────────────────────────────────────────────────
p = sync_playwright().start()
browser = p.chromium.launch(headless=True)

def scrape(user_name):
    url = f"{BASE_URL}?server={FIXED_SERVER}&name={quote(user_name)}"
    ctx = browser.new_context(user_agent=USER_AGENT)
    page = ctx.new_page()
    page.route("**/*.{png,jpg,jpeg,svg,gif,css,woff,woff2,ttf}", lambda r: r.abort())
    try:
        page.goto(url, wait_until='domcontentloaded', timeout=GOTO_TIMEOUT)
        page.wait_for_selector('div.scon', timeout=SELECTOR_TIMEOUT)
    except PlaywrightTimeoutError:
        ctx.close()
        return []

    items = []
    for scon in page.query_selector_all('div.scon'):
        # CharacterName
        name_el = scon.query_selector('div.seh_name span.name')
        char = name_el and page.evaluate('el => el.childNodes[0].nodeValue.trim()', name_el) or ''
        # Job
        job_el = scon.query_selector('div.seh_job li.sev')
        job = job_el.inner_text().strip() if job_el else ''
        # Reputation
        rep_el = scon.query_selector('div.seh_name div.level span.val')
        rep_raw = rep_el.inner_text().strip() if rep_el else ''
        rep_num = parse_int(''.join(filter(str.isdigit, rep_raw)))
        if rep_num <= 41929:
            continue
        # Buff Score
        buff_el = None
        is_buffer = False
        sb = scon.query_selector_all('div.seh_stat ul.stat_b li')
        if any('off' in (li.get_attribute('class') or '') for li in sb):
            buff_el = scon.query_selector('div.seh_stat ul.stat_b li div.statc span.val')
            is_buffer = True
        else:
            for li in sb:
                tl = li.query_selector('div.statc span.tl')
                if tl and tl.inner_text().strip() == '4인':
                    buff_el = li.query_selector('div.statc span.val')
                    is_buffer = True
                    break
            if not buff_el and sb:
                buff_el = sb[0].query_selector('div.statc span.val')
                is_buffer = True
        if not buff_el:
            sa = scon.query_selector('div.seh_stat ul.stat_a li div.statc span.val')
            buff_el = sa
        raw = buff_el.inner_text().strip() if buff_el else ''
        raw_clean = raw.replace(' ', '')

        if is_buffer:
            digits = ''.join(ch for ch in raw_clean if ch.isdigit())
            buff_val = int(digits) // 10000 if digits else 0
        else:
            if '억' in raw_clean:
                maj, aft = raw_clean.split('억', 1)
                nums = ''.join(ch for ch in aft if ch.isdigit())
                buff_val = float(f"{maj}.{nums[0]}") if nums else float(f"{maj}.0")
            else:
                buff_val = parse_buff(raw_clean)

        items.append({'label': None, 'char': char, 'job': job, 'rep': rep_num, 'buff': buff_val})
    ctx.close()
    return items

# ── 메인 ───────────────────────────────────────────────────
if __name__ == '__main__':
    groups = load_groups(GROUP_FILE)
    all_items = []
    for user, label in groups:
        scraped = scrape(user)
        for itm in scraped:
            itm['label'] = label
            all_items.append(itm)

    # 그룹 생성
    # 1) 흉몽: rep>52925, 각 label별 상위 4개
    h_items = []
    for label in set(i['label'] for i in all_items):
        lst = [i for i in all_items if i['label']==label and i['rep']>52925]
        top4 = sorted(lst, key=lambda x: x['rep'], reverse=True)[:4]
        h_items.extend(top4)
    # 2) 여신전: rep>48988
    y_items = [i for i in all_items if i['rep']>48988]
    # 3) 애쥬어: rep>44929, 흉몽 제외
    h_set = {(i['label'], i['char']) for i in h_items}
    a_items = [i for i in all_items if i['rep']>44929 and (i['label'], i['char']) not in h_set]
    # 4) 베누스: rep>41929
    b_items = [i for i in all_items if i['rep']>41929]

    def fmt(lst):
        return ", ".join(f"(\"{i['label']}\",\"{i['job']}\",{i['buff']})" for i in lst)

    # print Python dict literal
    import json
    groups = {
        "흉몽": h_items,
        "여신전": y_items,
        "애쥬어": a_items,
        "베누스": b_items
    }
    # stdout 에 순수 JSON 한 줄로 출력
    print(json.dumps(groups, ensure_ascii=False))
    browser.close()
    p.stop()
