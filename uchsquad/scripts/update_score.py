#scrap_char에서 서버 + 캐릭터 key 받아와서 갱신
#!/usr/bin/env python3
import sys
import subprocess
import ast
import requests
import sqlite3
import os
import datetime

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
    result = subprocess.run(cmd, capture_output=True, text=True, check=False, encoding='utf-8')
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
    
#버프력, 딜 score 추출
def extract_score_info(data):
    """
    API 응답 data에서 score와 isbuffer 플래그를 추출하여 반환합니다.
    - data: dict, API 응답
    Returns:
      score_n (int): 쉼표 제거 후 정수 변환된 점수
      isbuf_i (int): 버퍼 여부 (1: 버퍼, 0: 딜러)
    """
    buff_list = data.get('buffCal', [])
    buff_score = None
    if buff_list:
        last = buff_list[-1]
        buff_score = last.get('buffScoreNon') \
                     or last.get('4PBuffScore') \
                     or last.get('buffScore')

    if buff_score:
        raw = buff_score
        isbuf = 1
    else:
        ranking     = data.get('damageList', {}).get('vsRanking', [])
        total_entry = next((i for i in ranking if i.get('name') == '총 합'), {})
        raw         = total_entry.get('dam', data.get('score', '0'))
        isbuf       = 0

    clean = str(raw).replace(',', '')
    return int(clean), isbuf


def upsert_character(conn, data, server, key):
    # score와 isbuffer 추출
    score_n, isbuf_i = extract_score_info(data)

    # 필드 이스케이프 및 형 변환
    adventure = data['adventure'].replace("'", "''")
    server_s  = server.replace("'", "''")
    chara     = data['name'].replace("'", "''")
    job       = data['job'].replace("'", "''")
    fame_i    = int(data['fame'])

    # INSERT ... ON CONFLICT ... DO UPDATE
    sql = (
        "INSERT INTO user_character"
        " (adventure, server, key, chara_name, job, fame, score, last_score, isbuffer)"
        " VALUES"
        f" ('{adventure}', '{server_s}', '{key}', '{chara}', '{job}', {fame_i}, {score_n}, NULL, {isbuf_i})"
        " ON CONFLICT(adventure, server, chara_name) DO UPDATE SET"
        # 기존 score 를 last_score 에 복사
        " last_score = user_character.score,"
        # 새로 계산된 점수를 score 에 덮어씀
        " score      = excluded.score,"
        # 나머지 컬럼도 갱신
        " job        = excluded.job,"
        " fame       = excluded.fame,"
        " isbuffer   = excluded.isbuffer,"
        " key        = excluded.key;"
    )

    conn.execute(sql)
    


import datetime

def upsert_character_history(conn, data, server):
    """
    캐릭터 히스토리 테이블에
    - '다음 날 오전 6시'가 지나지 않았으면 UPDATE,
    - 경계 시간을 넘었으면 INSERT (새 이력 생성)
    updated_at은 항상 현재 시간(now)으로 기록
    """
    print(f"Updating score from API: {data['name']}")
    chara_name = data['name']
    fame_i     = int(data['fame'])
    server_s   = server
    score_n, _ = extract_score_info(data)

    # 1) 가장 최근 이력 조회
    row = conn.execute(
        '''
        SELECT idx, updated_at
          FROM character_history
         WHERE server=? AND chara_name=?
         ORDER BY updated_at DESC
         LIMIT 1
        ''',
        (server_s, chara_name)
    ).fetchone()

    now = datetime.datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")

    if row:
        # 2) 최근 이력의 경계 시각 계산: (row_date + 1일) 의 오전 6시
        last_dt = datetime.datetime.strptime(row['updated_at'], '%Y-%m-%d %H:%M:%S')
        next_day = last_dt.date() + datetime.timedelta(days=1)
        boundary_dt = datetime.datetime.combine(
            next_day,
            datetime.time(hour=6, minute=0, second=0)
        )

        if now < boundary_dt:
            # 경계 전: 같은 기간으로 간주 → UPDATE (updated_at도 갱신)
            conn.execute(
                '''
                UPDATE character_history
                   SET fame=?, score=?, updated_at=?
                 WHERE idx=?
                ''',
                (fame_i, score_n, now_str, row['idx'])
            )
            return

    # 3) 새 이력 INSERT (항상 now)
    conn.execute(
        '''
        INSERT INTO character_history
            (server, chara_name, fame, score, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ''',
        (server_s, chara_name, fame_i, score_n, now_str)
    )


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
                upsert_character_history(conn, data, server)
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
    print("DB 업데이트 완료")
