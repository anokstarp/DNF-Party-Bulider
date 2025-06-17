#!/usr/bin/env python3
import sys
import subprocess
import ast
import requests
import sqlite3
import os

# 스크립트 디렉터리 기준으로 scrap_char.py 절대경로
BASE_DIR        = os.path.dirname(os.path.abspath(__file__))
SCRAPE_SCRIPT   = os.path.join(BASE_DIR, 'scrap_char.py')
PYTHON_EXEC     = 'python'

# API 요청 URL 템플릿
REQUEST_TEMPLATE = "https://dundam.xyz/dat/viewData.jsp?image={key}&server={server}&"

# DB 파일 경로 (스크립트 위치 기준)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, '..', 'database', 'DB.sqlite')

def load_tuples_from_subprocess(keys):
    """scrap_char.py 를 호출해 (server, key) 튜플 리스트를 받아온다."""
    if not keys:
        return []

    cmd = [PYTHON_EXEC, SCRAPE_SCRIPT] + keys
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        print(f"스크랩 스크립트 오류 (exit code {result.returncode}):", file=sys.stderr)
        print(result.stderr.strip(), file=sys.stderr)
        return []

    tuples = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            tup = ast.literal_eval(line)
            if isinstance(tup, tuple) and len(tup) == 2:
                tuples.append(tup)
        except Exception:
            continue

    return tuples

def upsert_character(conn, data, server, key):
    """
    단일 응답 data 와 server/key 를 받아
    user_character 테이블에 INSERT or UPDATE 를 실행한다.
    """
    # 1) buffCal 마지막 항목의 buffScore 시도 추출
    buff_list  = data.get('buffCal', [])
    buff_score = buff_list[-1].get('buffScore') if buff_list else None

    if buff_score:
        score     = buff_score.replace(",", "")
        isbuffer  = 1
    else:
        # vsRanking에서 "총 합" dam
        ranking     = data.get('damageList', {}).get('vsRanking', [])
        total_entry = next((i for i in ranking if i.get('name') == '총 합'), None)
        score       = (total_entry or {}).get('dam', data.get('score', '0')).replace(",", "")
        isbuffer    = 0

    # 필드 이스케이프 및 형 변환
    adventure  = data['adventure'].replace("'", "''")
    server_s   = server.replace("'", "''")
    chara      = data['name'].replace("'", "''")
    job        = data['job'].replace("'", "''")
    fame_i     = int(data['fame'])
    score_n    = int(score)
    isbuf_i    = isbuffer

    # INSERT ... ON CONFLICT ... DO UPDATE
    sql = (
        "INSERT INTO user_character"
        " (adventure, server, chara_name, job, fame, score, last_score, isbuffer)"
        " VALUES"
        f" ('{adventure}', '{server_s}', '{chara}', '{job}', {fame_i}, {score_n}, NULL, {isbuf_i})"
        " ON CONFLICT(adventure, server, chara_name) DO UPDATE SET"
        # 기존 score 를 last_score 에 복사
        " last_score = user_character.score,"
        # 새로 계산된 점수를 score 에 덮어씀
        " score      = excluded.score,"
        # 나머지 컬럼도 갱신
        " job        = excluded.job,"
        " fame       = excluded.fame,"
        " isbuffer   = excluded.isbuffer;"
    )

    conn.execute(sql)

def fetch_and_update(tuples):
    """
    server–key 튜플 리스트를 받아, API 호출 후
    DB에 INSERT/UPDATE 를 수행한다.
    """
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})

    # DB 연결
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    for server, key in tuples:
        url = REQUEST_TEMPLATE.format(server=server, key=key)
        try:
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            if 'adventure' in data and 'name' in data:
                upsert_character(conn, data, server, key)
            else:
                print(f"-- {server} : {key} 갱신 실패 (응답 형식 오류)")
        except requests.RequestException as e:
            print(f"-- {server} : {key} 갱신 실패 (에러: {e})")

    conn.commit()
    conn.close()

if __name__ == '__main__':
    # 1) 커맨드라인 인자로 넘어온 key 리스트
    keys = sys.argv[1:]  # ex: ['ABC123', 'DEF456', ...]

    # 2) scrap_char.py 호출해 (server, key) 튜플 리스트 획득
    server_char_tuples = load_tuples_from_subprocess(keys)
    if not server_char_tuples:
        print("유효한 서버/키 튜플이 없습니다. 스크랩 스크립트 확인 필요.")
        sys.exit(1)

    # 3) API 호출 및 DB 반영
    fetch_and_update(server_char_tuples)
    print("DB 업데이트 완료 ✔")
