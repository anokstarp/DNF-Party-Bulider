#!/usr/bin/env python3
import sys
import sqlite3
import pandas as pd
import numpy as np
import os
import argparse
import json

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def load_characters(db_path, role=None):
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database file not found: {db_path}")
    conn = sqlite3.connect(db_path)

    buf_query = """
        SELECT adventure, chara_name, job, fame, score, isbuffer, temple, azure, venus
        FROM user_character
        WHERE use_yn = 1
          AND isbuffer = 1
    """
    if role in ('temple', 'azure', 'venus'):
        buf_query += f" AND {role} = 1"
    buf_df = pd.read_sql_query(buf_query, conn)

    del_query = """
        SELECT adventure, chara_name, job, fame, score, isbuffer, temple, azure, venus
        FROM user_character
        WHERE use_yn = 1
          AND isbuffer = 0
    """
    if role in ('temple', 'azure', 'venus'):
        del_query += f" AND {role} = 1"
    del_df = pd.read_sql_query(del_query, conn)

    conn.close()
    return buf_df, del_df


def compute_points(buf_df, del_df):
    bufs = buf_df.copy()
    dels = del_df.copy()
    bufs['point'] = bufs['score'] / 3_000_000.0
    dels['point'] = dels['score']
    return bufs.to_dict('records'), dels.to_dict('records')


def match_parties_balanced(buffers, dealers):
    all_people = buffers + dealers
    party_cnt = min(len(buffers), len(all_people)//4)
    parties = [[] for _ in range(party_cnt)]
    party_advs = [set() for _ in range(party_cnt)]

    # 버퍼(점수순) 파티별 한명씩
    sorted_buffers = sorted(buffers, key=lambda x: -x['score'])
    for i, buf in enumerate(sorted_buffers[:party_cnt]):
        parties[i].append(buf)
        party_advs[i].add(buf['adventure'])

    # 딜러(점수순) 남는 파티에 adventure 중복 없이 분배
    sorted_dealers = sorted(dealers, key=lambda x: -x['score'])
    for dealer in sorted_dealers:
        best_idx, best_score = None, None
        for idx in range(party_cnt):
            if len(parties[idx]) < 4 and dealer['adventure'] not in party_advs[idx]:
                temp = parties[idx]+[dealer]
                score = compute_party_score(temp)
                if best_score is None or score < best_score:
                    best_idx, best_score = idx, score
        if best_idx is not None:
            parties[best_idx].append(dealer)
            party_advs[best_idx].add(dealer['adventure'])

    # DB에 맞게 포맷 변환
    party_objs = []
    for party in parties:
        buf = next((m for m in party if m['isbuffer']), None)
        dealers_in_party = [m for m in party if not m['isbuffer']]
        party_score = compute_party_score(party)
        party_objs.append({'buffers':[buf] if buf else [], 'dealers':dealers_in_party, 'party_score':party_score})

    assigned = set((m['adventure'], m['chara_name']) for p in parties for m in p)
    unassigned = [c for c in all_people if (c['adventure'], c['chara_name']) not in assigned]
    skipped = []
    return party_objs, unassigned, skipped

def compute_party_score(members):
    buffers = [m for m in members if m['isbuffer']]
    dealers = [m for m in members if not m['isbuffer']]
    main_buff = max(buffers, key=lambda x: x['score']) if buffers else None
    sub_buff = max([b for b in buffers if b != main_buff], key=lambda x: x['score']) if buffers and len(buffers) > 1 else None

    buff_factor = (main_buff['score'] / 3_000_000) if main_buff else 1.0
    dealer_sum = sum(d['score'] // 10_000_000 for d in dealers)
    sub_buff_factor = 1.0
    if sub_buff:
        sub_buff_factor = 1 + (sub_buff['score'] / 1_000_000) * 0.08
    return buff_factor * dealer_sum * sub_buff_factor



if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Generate parties, print results, and insert into DB')
    parser.add_argument('role', nargs='?', choices=['temple','azure','venus'], default=None)
    args = parser.parse_args()

    base = os.path.dirname(os.path.abspath(__file__)) + '/..'
    db_path = os.path.join(base, 'database', 'DB.sqlite')

    buf_df, del_df = load_characters(db_path, args.role)
    print("=== All Characters ===")
    all_df = pd.concat([buf_df, del_df], ignore_index=True)
    print(all_df[['adventure','chara_name','job','fame','score','isbuffer']].to_string(index=False))

    buffers, dealers = compute_points(buf_df, del_df)
    parties, unassigned, skipped = match_parties_balanced(buffers, dealers)

    print(f"Loaded: total={len(buffers)+len(dealers)} (buffers={len(buffers)}, dealers={len(dealers)})\n")
    for i, p in enumerate(parties, 1):
        b = p['buffers'][0]
        print(f"Party {i}: Buffer: {b['adventure']}—{b['chara_name']}({b['score']:,})")
        for j, d in enumerate(p['dealers'], 1): print(f"  Dealer{j}: {d['adventure']}—{d['chara_name']}({d['score']:,})")
        print(f"  Combined: {p['party_score']:.2f}\n")

    print("=== Skipped Incomplete Parties ===")
    for s in skipped:
        buf_name = s['buffer']['chara_name'] if s['buffer'] else 'None'
        dealer_name = s['dealer']['chara_name'] if s['dealer'] else 'None'
        print(f"Party Attempt {s['party_index']}: Buffer={buf_name}, Dealer={dealer_name}, Lows Selected={s['lows_count']}/2")
    print(f"Total skipped: {len(skipped)}\n")

    print("=== Unassigned ===")
    for c in unassigned:
        role_lbl = "버퍼" if c['isbuffer'] == 1 else "딜러"
        print(f"[{role_lbl}] {c['adventure']}—{c['chara_name']}({c['score']:,})")
    print(f"총 {len(unassigned)}명 남음\n")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    tval = args.role or 'all'
    cur.execute("DELETE FROM party WHERE type = ?", (tval,))
    cur.execute("DELETE FROM abandonment WHERE type = ?", (tval,))
    for p in parties:
        buf = p['buffers'][0]
        buf_j = json.dumps({k: buf[k] for k in ('adventure','chara_name','job','fame','score')}, ensure_ascii=False)
        dj = [json.dumps({k: d[k] for k in ('adventure','chara_name','job','fame','score')}, ensure_ascii=False) for d in p['dealers'][:3]]
        dj += [''] * (3 - len(dj))
        cur.execute(
            "INSERT INTO party(type, buffer, dealer1, dealer2, dealer3, result) VALUES(?,?,?,?,?,?)",
            (tval, buf_j, dj[0], dj[1], dj[2], p['party_score'])
        )
    for c in unassigned:
        cur.execute(
            "INSERT INTO abandonment(type, character) VALUES(?,?)",
            (tval, json.dumps(c, ensure_ascii=False))
        )
    conn.commit()
    conn.close()
    print(f"→ DB에 {len(parties)}개 파티와 {len(unassigned)}명 남은 캐릭터 저장 완료 (type={tval})")

