#!/usr/bin/env python3
import sys
import sqlite3
import os
import requests
import datetime

# DB 파일 경로
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, '..', 'database', 'DB.sqlite')

# API 요청 URL 템플릿
REQUEST_TEMPLATE = "https://dundam.xyz/dat/viewData.jsp?image={key}&server={server}&"

def extract_score_info(data):
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
    score_n, isbuf_i = extract_score_info(data)
    adventure = data['adventure'].replace("'", "''")
    server_s  = server.replace("'", "''")
    chara     = data['name'].replace("'", "''")
    job       = data['job'].replace("'", "''")
    fame_i    = int(data['fame'])

    sql = (
        "INSERT INTO user_character"
        " (adventure, server, key, chara_name, job, fame, score, last_score, isbuffer)"
        " VALUES"
        f" ('{adventure}', '{server_s}', '{key}', '{chara}', '{job}', {fame_i}, {score_n}, NULL, {isbuf_i})"
        " ON CONFLICT(adventure, server, chara_name) DO UPDATE SET"
        " last_score = user_character.score,"
        " score      = excluded.score,"
        " job        = excluded.job,"
        " fame       = excluded.fame,"
        " isbuffer   = excluded.isbuffer,"
        " key        = excluded.key;"
    )

    conn.execute(sql)

def upsert_character_history(conn, data, server):
    print(f"Updating score from API: {data['name']}")
    chara_name = data['name']
    fame_i     = int(data['fame'])
    server_s   = server
    score_n, _ = extract_score_info(data)

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
        last_dt = datetime.datetime.strptime(row['updated_at'], '%Y-%m-%d %H:%M:%S')
        next_day = last_dt.date() + datetime.timedelta(days=1)
        boundary_dt = datetime.datetime.combine(
            next_day,
            datetime.time(hour=6, minute=0, second=0)
        )
        if now < boundary_dt:
            conn.execute(
                '''
                UPDATE character_history
                   SET fame=?, score=?, updated_at=?
                 WHERE idx=?
                ''',
                (fame_i, score_n, now_str, row['idx'])
            )
            return

    conn.execute(
        '''
        INSERT INTO character_history
            (server, chara_name, fame, score, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ''',
        (server_s, chara_name, fame_i, score_n, now_str)
    )

def fetch_and_update(tuples):
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})

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

def get_tuples_from_db(adventure):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        '''
        SELECT server, key
          FROM user_character
         WHERE adventure = ?
        ''',
        (adventure,)
    ).fetchall()
    conn.close()
    return [(r['server'], r['key']) for r in rows]

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("사용법: python update_score_from_db.py <모험단명>")
        sys.exit(1)

    adventure = sys.argv[1]
    tuples = get_tuples_from_db(adventure)
    if not tuples:
        print("해당 모험단에 등록된 캐릭터가 없습니다.")
        sys.exit(1)

    fetch_and_update(tuples)
    print("DB 업데이트 완료 ✔")
