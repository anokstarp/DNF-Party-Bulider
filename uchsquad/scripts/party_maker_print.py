#!/usr/bin/env python3
import sys
import sqlite3
import pandas as pd
import numpy as np
import os
import random
import argparse
import json

# Windows 콘솔에서도 유니코드 출력 가능하도록 stdout 인코딩을 UTF-8로 재설정
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# 1) DB에서 use_yn=1인 활성 캐릭터 로드: 버퍼(isbuffer=1)와 딜러(isbuffer=0)를 분리
def load_characters(db_path, role=None):
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database file not found: {db_path}")
    conn = sqlite3.connect(db_path)

    # 버퍼만 로드
    buf_query = """
        SELECT adventure, chara_name, job, fame, score, isbuffer
        FROM user_character
        WHERE use_yn = 1
          AND isbuffer = 1
    """
    if role in ('temple', 'azure', 'venus'):
        buf_query += f" AND {role} = 1"
    buf_df = pd.read_sql_query(buf_query, conn)

    # 딜러만 로드 (역할 필터 없이 모든 활성 딜러)
    del_query = """
        SELECT adventure, chara_name, job, fame, score, isbuffer
        FROM user_character
        WHERE use_yn = 1
          AND isbuffer = 0
    """
    del_df = pd.read_sql_query(del_query, conn)

    conn.close()
    return buf_df, del_df

# 2) 점수 → 포인트 환산 및 dict 변환
def compute_points(buf_df, del_df):
    bufs = buf_df.copy()
    dels = del_df.copy()
    # 버퍼는 score / 3,000,000
    bufs['point'] = bufs['score'] / 3_000_000.0
    # 딜러는 (score // 1,000,000) / 10
    dels['point'] = (dels['score'] // 1_000_000) / 10.0
    return bufs.to_dict('records'), dels.to_dict('records')

# --- 여기부터 개선된 파티 매칭 로직 ---

def match_parties_max_full(buffers, dealers):
    # 점수 내림차순 정렬
    sorted_buffers = sorted(buffers, key=lambda x: -x['score'])
    sorted_dealers = sorted(dealers, key=lambda x: -x['score'])

    # 만들 수 있는 최대 파티 수
    party_count = min(len(sorted_buffers), len(sorted_dealers) // 3)
    parties = []

    # 파티마다 버퍼 1명, 딜러 3명 할당
    for i in range(party_count):
        buf = sorted_buffers[i]
        # **딜러 분배: 상/중/하 점수 섞어서 할당**
        d1 = sorted_dealers[i]  # 상위
        d2 = sorted_dealers[-(i+1)]  # 하위
        mid_idx = len(sorted_dealers) // 2 + (i if i < len(sorted_dealers)//2 else 0)
        if mid_idx >= len(sorted_dealers): mid_idx = i  # 오버시 상위로 대체
        d3 = sorted_dealers[mid_idx]
        # 중복 방지 (동일 캐릭 할당 가능성 제거)
        dealer_ids = {id(d1), id(d2), id(d3)}
        if len(dealer_ids) < 3:  # 겹침 발생 시 가장 가까운 안 겹치는 놈 찾아서 배정
            remain = [d for d in sorted_dealers if id(d) not in dealer_ids]
            while len(dealer_ids) < 3 and remain:
                d_new = remain.pop(0)
                dealer_ids.add(id(d_new))
            d1, d2, d3 = [d for d in sorted_dealers if id(d) in dealer_ids][:3]

        dealers_for_party = [d1, d2, d3]

        # 파티 점수 계산식: 버퍼점수 / 300 * (딜러 점수합)
        party_score = buf['score'] / 300 * sum(d['score'] for d in dealers_for_party)

        parties.append({
            'buffers': [buf],
            'dealers': dealers_for_party,
            'party_score': party_score,
        })

    # 할당된 캐릭터 id
    used_ids = set()
    for p in parties:
        used_ids.add(id(p['buffers'][0]))
        for d in p['dealers']:
            used_ids.add(id(d))

    # 미할당 리스트
    all_chars = buffers + dealers
    unassigned = [c for c in all_chars if id(c) not in used_ids]

    return parties, unassigned



# ------------------------------

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Generate parties, print results, and insert into DB'
    )
    parser.add_argument('role', nargs='?', choices=['temple','azure','venus'], default=None,
                        help="Role filter for buffers")
    args = parser.parse_args()

    # DB 경로 설정
    base    = os.path.dirname(os.path.abspath(__file__)) + '/..'
    db_path = os.path.join(base, 'database', 'DB.sqlite')

    # 1) 캐릭터 로드 2) 포인트 계산
    buf_df, del_df       = load_characters(db_path, args.role)
    buffers, dealers     = compute_points(buf_df, del_df)

    # 3) 파티 생성 (개선된 매칭 사용)
    parties = match_parties_max_full(buffers, dealers)

    # 남은 캐릭터 계산
    assigned_ids = {id(x) for p in parties for x in (p['buffers'] + p['dealers'])}
    all_chars   = buffers + dealers
    unassigned  = [c for c in all_chars if id(c) not in assigned_ids]

    # 콘솔 출력
    print(f"Loaded: total={len(buffers)+len(dealers)} "
          f"(buffers={len(buffers)}, dealers={len(dealers)})\n")
    for i, p in enumerate(parties, 1):
        b = p['buffers'][0]
        print(f"Party {i}: Buffer: {b['adventure']}—{b['chara_name']}({b['score']:,})")
        for j, d in enumerate(p['dealers'], 1):
            print(f"  Dealer{j}: {d['adventure']}—{d['chara_name']}({d['score']:,})")
        print(f"  Combined: {p['party_score']:.2f}\n")
    print("=== Unassigned ===")
    for c in unassigned:
        role_lbl = "버퍼" if c['isbuffer'] == 1 else "딜러"
        print(f"[{role_lbl}] {c['adventure']}—{c['chara_name']}({c['score']:,})")
    print(f"총 {len(unassigned)}명 남음\n")

    # DB 갱신: party, abandonment 테이블 모두 삭제 후 재삽입
    conn = sqlite3.connect(db_path)
    cur  = conn.cursor()
    tval = args.role or 'all'

    cur.execute("DELETE FROM party WHERE type = ?", (tval,))
    cur.execute("DELETE FROM abandonment WHERE type = ?", (tval,))

    # party 삽입
    for p in parties:
        buf = p['buffers'][0]
        buf_j = json.dumps({k: buf[k] for k in ('adventure','chara_name','job','fame','score')}, ensure_ascii=False)
        dj = []
        for d in p['dealers'][:3]:
            dj.append(json.dumps({k: d[k] for k in ('adventure','chara_name','job','fame','score')}, ensure_ascii=False))
        dj += [''] * (3 - len(dj))
        cur.execute(
            "INSERT INTO party(type, buffer, dealer1, dealer2, dealer3, result) VALUES(?,?,?,?,?,?)",
            (tval, buf_j, dj[0], dj[1], dj[2], p['party_score'])
        )

    # abandonment 삽입
    for c in unassigned:
        cur.execute(
            "INSERT INTO abandonment(type, character) VALUES(?,?)",
            (tval, json.dumps(c, ensure_ascii=False))
        )

    conn.commit()
    conn.close()
    print(f"→ DB에 {len(parties)}개 파티와 {len(unassigned)}명 남은 캐릭터 저장 완료 (type={tval})")
