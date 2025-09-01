# scripts/party_generator.py

import sqlite3
import json
from app import get_db_connection  # Flask 앱의 DB 커넥션 사용

def get_characters(attr: str) -> list[dict]:
    """
    use_yn=1 캐릭터 중에서
    attr 컬럼(temple/azure/venus/tmp)이 1인 캐릭터를
    adventure, chara_name, job, score, isbuffer 로 반환
    """
    conn = get_db_connection()
    # Row 객체로 반환되도록 설정
    conn.row_factory = sqlite3.Row

    cur = conn.cursor()
    cur.execute(f"""
        SELECT adventure, chara_name, job, score, isbuffer
        FROM user_character
        WHERE use_yn = 1
          AND {attr} = 1
        ORDER BY idx
    """)
    rows = cur.fetchall()
    conn.close()

    return [
        {
            'adventure': r['adventure'],
            'chara_name': r['chara_name'],
            'job':        r['job'],
            'score':      r['score'],
            'isbuffer':   r['isbuffer']
        }
        for r in rows
    ]

def build_parties(char_list: list[dict]) -> list[dict]:
    buffers = [c for c in char_list if c['isbuffer'] == 1]
    dealers = [c for c in char_list if c['isbuffer'] == 0]
    parties = []
    di = 0

    for buf in buffers:
        party = {'buffer': buf, 'dealers': []}
        for _ in range(3):
            if di < len(dealers):
                party['dealers'].append(dealers[di])
                di += 1
            else:
                party['dealers'].append(None)
        parties.append(party)

    if di < len(dealers):
        party = {'buffer': None, 'dealers': []}
        while di < len(dealers):
            party['dealers'].append(dealers[di])
            di += 1
        while len(party['dealers']) < 3:
            party['dealers'].append(None)
        parties.append(party)

    return parties

def clear_party(party_type: str):
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute('DELETE FROM party WHERE type = ?', (party_type,))
    conn.commit()
    conn.close()

def insert_party(party_type: str, parties: list[dict]):
    conn = get_db_connection()
    cur  = conn.cursor()
    for p in parties:
        buff = json.dumps(p['buffer'], ensure_ascii=False) if p['buffer'] else None
        dealers = [json.dumps(d, ensure_ascii=False) if d else None for d in p['dealers']]
        cur.execute("""
            INSERT INTO party (type, buffer, dealer1, dealer2, dealer3)
            VALUES (?, ?, ?, ?, ?)
        """, [party_type, buff] + dealers)
    conn.commit()
    conn.close()

def run_party_generation(party_type: str):
    chars = get_characters(party_type)
    parties = build_parties(chars)
    clear_party(party_type)
    insert_party(party_type, parties)
