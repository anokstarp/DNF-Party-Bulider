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

# 3) 파티 생성 수 계산: 버퍼 수와 전체 캐릭터 수 기반
def calc_party_count(buffers, dealers):
    total = len(buffers) + len(dealers)
    return min(len(buffers), total // 4)

# 4) 편차 줄이기 위한 최적화 (여기서는 스텁)
def optimize_parties(parties, iterations=1000):
    def std(p_list):
        scores = [p['party_score'] for p in p_list if len(p['buffers']) + len(p['dealers']) == 4]
        return np.std(scores) if scores else 0

    best_std = std(parties)
    # 최적화 로직이 필요하다면 여기에 구현
    return parties

# 5) 파티 매칭 로직
def match_parties(buffers, dealers):
    party_count    = calc_party_count(buffers, dealers)
    buffers_sorted = sorted(buffers, key=lambda x: x['point'], reverse=True)
    deals_desc     = sorted(dealers, key=lambda x: x['score'], reverse=True)
    deals_asc      = sorted(dealers, key=lambda x: x['score'])

    # 초기화: 각 파티에 버퍼 1명 할당
    parties = []
    for i in range(party_count):
        parties.append({
            'buffers': [buffers_sorted[i]],
            'dealers': [],
            'advs':    {buffers_sorted[i]['adventure']}
        })

    # 5-1) 약한 버퍼 파티부터 강한 딜러 1명 할당
    buf_weak_order = sorted(range(party_count),
                             key=lambda i: parties[i]['buffers'][0]['point'])
    for idx in buf_weak_order:
        for d in deals_desc[:]:
            if d['adventure'] not in parties[idx]['advs']:
                parties[idx]['dealers'].append(d)
                parties[idx]['advs'].add(d['adventure'])
                deals_desc.remove(d)
                deals_asc.remove(d)
                break

    # 5-2) 강한 딜러(>50억) 파티에 약한 딜러 2명 추가
    TH = 5_000_000_000
    def max_dealer_score(p):
        return max((d['score'] for d in p['dealers']), default=0)
    order_strong = sorted(parties, key=max_dealer_score, reverse=True)
    for p in order_strong:
        if max_dealer_score(p) > TH:
            cnt = 0
            for d in deals_asc[:]:
                if d['adventure'] not in p['advs']:
                    p['dealers'].append(d)
                    p['advs'].add(d['adventure'])
                    deals_asc.remove(d)
                    deals_desc.remove(d)
                    cnt += 1
                    if cnt == 2:
                        break

    # 5-3) 남는 버퍼 → 다음 강한 파티 순으로 1명씩 딜러로 할당
    leftover_bufs = buffers_sorted[party_count:]
    for buf in leftover_bufs:
        for p in order_strong:
            if buf['adventure'] not in p['advs'] and len(p['buffers']) + len(p['dealers']) < 4:
                p['dealers'].append(buf)
                p['advs'].add(buf['adventure'])
                p['_got_buffer_as_dealer'] = True
                break

    # 5-4) 남는 딜러 반복 배정
    while True:
        assigned = False
        for p in order_strong:
            if len(p['buffers']) + len(p['dealers']) >= 4:
                continue
            pool = deals_desc if p.get('_got_buffer_as_dealer') else deals_asc
            for d in pool:
                if d['adventure'] not in p['advs']:
                    p['dealers'].append(d)
                    p['advs'].add(d['adventure'])
                    if d in deals_asc:  deals_asc.remove(d)
                    if d in deals_desc: deals_desc.remove(d)
                    assigned = True
                    break
        if not assigned:
            break

    # 스코어 계산 & advs 제거
    for p in parties:
        buf_pts  = sum(b['point'] for b in p['buffers'])
        deal_pts = sum(d['point'] for d in p['dealers'])
        p['party_score'] = buf_pts * deal_pts
        del p['advs']

    # 6) 편차 최적화
    return optimize_parties(parties)

# 7) 메인 실행부: 콘솔 출력 & DB 삽입 (party 테이블 + abandonment 테이블)
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

    # 3) 파티 생성
    parties = match_parties(buffers, dealers)

    # 남은 캐릭터 계산
    assigned    = {tuple(x.items()) for p in parties for x in (p['buffers'] + p['dealers'])}
    all_chars   = buffers + dealers
    unassigned  = [c for c in all_chars if tuple(c.items()) not in assigned]

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
