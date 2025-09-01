import os

# Create the scripts directory if it doesn't exist
os.makedirs('/mnt/data/scripts', exist_ok=True)

script_content = '''#!/usr/bin/env python3
# scripts/generate_parties.py

import sqlite3
import json
import argparse
import sys

DB_PATH = 'your_database.db'

TYPE_TABLE_MAP = {
    'temple': 'temple_party',
    'azure': 'azure_party',
    'venus': 'venus_party',
    'tmp': 'tmp_party'
}

def get_characters(attr):
    """
    use_yn=1 캐릭터 중에서
    attr 컬럼이 1인 캐릭터만 adventure, chara_name, job, score, isbuffer 로 반환
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(f"""
        SELECT adventure, chara_name, job, score, isbuffer
        FROM user_character
        WHERE use_yn=1 AND {attr}=1
        ORDER BY idx
    """)
    rows = cur.fetchall()
    conn.close()
    return [
        {
            'adventure': r[0],
            'chara_name': r[1],
            'job': r[2],
            'score': r[3],
            'isbuffer': r[4]
        } for r in rows
    ]

def clear_party_table(table):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(f"DELETE FROM {table}")
    conn.commit()
    conn.close()

def insert_party(table, party_list):
    """
    party_list: [
      {'buffer': {...}, 'dealers': [{...}, {...}, {...}]},
      ...
    ]
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    for p in party_list:
        buff_json = json.dumps(p['buffer'], ensure_ascii=False) if p['buffer'] else None
        dealers = p['dealers']
        dealer_jsons = [json.dumps(d, ensure_ascii=False) if d else None for d in dealers]
        cur.execute(f"""
            INSERT INTO {table} (buffer, dealer1, dealer2, dealer3)
            VALUES (?, ?, ?, ?)
        """, [buff_json] + dealer_jsons)
    conn.commit()
    conn.close()

def build_parties(char_list):
    """
    간단히 순서대로 buffer 1명 + 다음 3명 dealers 로 묶음
    """
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
    # 남은 dealers 처리 (빈 buffer로 파티 생성)
    if di < len(dealers):
        party = {'buffer': None, 'dealers': []}
        while di < len(dealers):
            party['dealers'].append(dealers[di])
            di += 1
        # 빈 칸 채우기
        while len(party['dealers']) < 3:
            party['dealers'].append(None)
        parties.append(party)
    return parties

def main():
    parser = argparse.ArgumentParser(
        description='temple/azure/venus/tmp 파티를 생성해 DB에 저장하는 스크립트')
    parser.add_argument('type', choices=list(TYPE_TABLE_MAP.keys()) + ['all'],
                        help='생성할 파티 유형 또는 all')
    args = parser.parse_args()

    types_to_run = TYPE_TABLE_MAP.keys() if args.type == 'all' else [args.type]

    for t in types_to_run:
        print(f'Processing {t} party...')
        chars = get_characters(t)
        parties = build_parties(chars)
        table = TYPE_TABLE_MAP[t]
        clear_party_table(table)
        insert_party(table, parties)
        print(f'  -> Inserted {len(parties)} parties into {table}')

if __name__ == '__main__':
    main()
'''

# Write the script file
script_path = '/mnt/data/scripts/generate_parties.py'
with open(script_path, 'w', encoding='utf-8') as f:
    f.write(script_content)

# Make the script executable
os.chmod(script_path, 0o755)

script_path
