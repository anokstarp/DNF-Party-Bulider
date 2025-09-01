#!/usr/bin/env python3
import sys
import sqlite3
import pandas as pd
import os
import argparse
import json
import math
from collections import Counter
from typing import List, Optional, Tuple
from statistics import stdev

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# DB에서 캐릭터 불러오기
def load_characters(db_path, role=None):
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database file not found: {db_path}")
    conn = sqlite3.connect(db_path)

    buf_query = '''
        SELECT adventure, chara_name, job, fame, score, isbuffer, temple, azure, venus, tmp
        FROM user_character
        WHERE use_yn = 1
          AND isbuffer = 1
    '''
    if role in ('temple', 'azure', 'venus', 'tmp'):
        buf_query += f" AND {role} = 1"
    buf_df = pd.read_sql_query(buf_query, conn)

    del_query = '''
        SELECT adventure, chara_name, job, fame, score, isbuffer, temple, azure, venus, tmp
        FROM user_character
        WHERE use_yn = 1
          AND isbuffer = 0
    '''
    if role in ('temple', 'azure', 'venus', 'tmp'):
        del_query += f" AND {role} = 1"
    del_df = pd.read_sql_query(del_query, conn)

    conn.close()
    return buf_df, del_df

# DB 포맷(dict)을 create_parties_alternative용 포맷으로 변환
def adapt_characters(records):
    def adapt_one(r):
        return {
            "is_buffer": bool(r.get("isbuffer", r.get("is_buffer", False))),
            "score": r["score"],
            "account": r.get("adventure", r.get("account", "")),
            "name": r.get("chara_name", r.get("name", "")),
            "job": r.get("job", ""),
            "fame": r.get("fame", 0),
        }
    return [adapt_one(r) for r in records]

# 파티 점수 계산
def compute_party_score(members):
    buffers = [m for m in members if m['is_buffer']]
    dealers = [m for m in members if not m['is_buffer']]
    main_buff = max(buffers, key=lambda x: x['score']) if buffers else None
    sub_buff = max([b for b in buffers if b != main_buff], key=lambda x: x['score']) if len(buffers) > 1 else None

    buff_factor = (main_buff['score'] / 3_000_000) if main_buff else 1.0
    dealer_sum = sum(d['score'] // 10_000_000 for d in dealers)
    sub_buff_factor = 1.0
    if sub_buff:
        sub_buff_factor = 1 + (sub_buff['score'] / 1_200_000) * 0.08
    return buff_factor * dealer_sum * sub_buff_factor


# 파티 배정 함수
def assign_parties(
    characters: List[dict]
) -> Optional[Tuple[List[List[dict]], List[dict], List[float], float, float]]:
    # 1) 키 정규화
    for c in characters:
        if "account" in c and "adventure" not in c:
            c["adventure"] = c["account"]
        if "name" in c and "chara_name" not in c:
            c["chara_name"] = c["name"]

    total = len(characters)
    buffers = [c for c in characters if c['is_buffer']]
    dealers = [c for c in characters if not c['is_buffer']]

    # ----- 각 모험단별 전체 캐릭터 수 계산 -----
    adv_counts = Counter(c['adventure'] for c in characters)

    # 2) 파티 수 결정 (buffer×1+, dealer×3, total×4 기준 floor)
    P = min(len(buffers), total // 4)
    if P == 0:
        # 파티 없음 → 모두 leftover
        return [], characters[:], [], 0.0, 0.0

    # 3) 파티 초기화
    parties = [{'members': [], 'adventures': set()} for _ in range(P)]
    leftover = []

    # 4) 버퍼 1명씩 Round-Robin 배치 (모험단 인원수 우선 + score 순)
    buffs_sorted = sorted(
        buffers,
        key=lambda c: (adv_counts[c['adventure']], c['score']),
        reverse=True
    )
    # mark main buffers
    for buf in buffs_sorted:
        buf['_is_main_buffer'] = False
    for i, buf in enumerate(buffs_sorted[:P]):
        buf['_is_main_buffer'] = True
        parties[i]['members'].append(buf)
        parties[i]['adventures'].add(buf['adventure'])
    leftover_bufs = buffs_sorted[P:]

    # mark sub-buffers
    for buf in leftover_bufs:
        buf['_is_main_buffer'] = False

    # 5) 딜러 배치 (모험단 인원수 우선 + score 순)
    # ensure dealers marked as non-main buffers
    for d in dealers:
        d['_is_main_buffer'] = False
    dlrs_sorted = sorted(
        dealers,
        key=lambda c: (adv_counts[c['adventure']], c['score']),
        reverse=True
    )
    for dlr in dlrs_sorted:
        cands = [p for p in parties
                 if len(p['members']) < 4
                    and dlr['adventure'] not in p['adventures']]
        if not cands:
            leftover.append(dlr)
            continue
        best = min(
            cands,
            key=lambda p: (
                len(p['members']),
                compute_party_score(p['members'] + [dlr])
            )
        )
        best['members'].append(dlr)
        best['adventures'].add(dlr['adventure'])

    # 6) 남은 슬롯에 버퍼 추가 (파티당 최대 2명)
    for p in parties:
        if len(p['members']) < 4:
            for buf in list(leftover_bufs):
                if (buf['adventure'] not in p['adventures'] and
                    sum(m['is_buffer'] for m in p['members']) < 2):
                    p['members'].append(buf)
                    p['adventures'].add(buf['adventure'])
                    leftover_bufs.remove(buf)
                    break
    # combine leftovers
    all_leftovers = leftover + leftover_bufs
    leftover = []

    # helper for swap eligibility
    def can_swap(c, m):
        # main-buffer swaps only with main-buffer
        if c['is_buffer'] and c.get('_is_main_buffer', False):
            return m['is_buffer'] and m.get('_is_main_buffer', False)
        # dealer can swap with dealer or sub-buffer
        if not c['is_buffer']:
            return (not m['is_buffer']) or (m['is_buffer'] and not m.get('_is_main_buffer', False))
        # sub-buffer swaps only with dealer
        if c['is_buffer'] and not c.get('_is_main_buffer', False):
            return not m['is_buffer']
        return False

    # 6.5) 남은 캐릭터를 빈 슬롯에 빈틈 없도록 swap 시도
    for c in list(all_leftovers):
        placed = False
        for p in parties:
            if len(p['members']) >= 4:
                continue
            # 1) 직접 삽입 시도
            if (c['adventure'] not in p['adventures'] and
                (not c['is_buffer'] or sum(m['is_buffer'] for m in p['members']) < 2)):
                p['members'].append(c)
                p['adventures'].add(c['adventure'])
                all_leftovers.remove(c)
                placed = True
                break
            # 2) swap 시도
            for q in parties:
                if q is p:
                    continue
                # c가 q에 들어갈 수 있어야 함
                if c['adventure'] in q['adventures']:
                    continue
                # q로부터 m 선택
                for m in list(q['members']):
                    # m은 p에 들어갈 수 있어야 함
                    if m['adventure'] in p['adventures']:
                        continue
                    # 타입 제약
                    if not can_swap(c, m):
                        continue
                    # 버퍼 수 제약
                    buf_p = sum(mm['is_buffer'] for mm in p['members']) + m['is_buffer']
                    buf_q = sum(mm['is_buffer'] for mm in q['members']) - m['is_buffer'] + c['is_buffer']
                    if buf_p < 1 or buf_p > 2 or buf_q < 1 or buf_q > 2:
                        continue
                    # swap 수행
                    q['members'].remove(m)
                    q['adventures'].remove(m['adventure'])
                    p['members'].append(m)
                    p['adventures'].add(m['adventure'])
                    q['members'].append(c)
                    q['adventures'].add(c['adventure'])
                    all_leftovers.remove(c)
                    placed = True
                    break
                if placed:
                    break
            if placed:
                break
        if not placed:
            leftover.append(c)

    # 7) 편차 줄이기 스왑 (최대 5000회)
    for _ in range(5000):
        scores = [compute_party_score(p['members']) for p in parties]
        curr_std = stdev(scores) if len(scores) > 1 else 0.0
        best_swap = None
        for i in range(P):
            for j in range(i+1, P):
                for m1 in parties[i]['members']:
                    for m2 in parties[j]['members']:
                        adv_i = {m['adventure'] for m in parties[i]['members'] if m is not m1}
                        adv_j = {m['adventure'] for m in parties[j]['members'] if m is not m2}
                        buf_i = (sum(m['is_buffer'] for m in parties[i]['members'])
                                 - m1['is_buffer'] + m2['is_buffer'])
                        buf_j = (sum(m['is_buffer'] for m in parties[j]['members'])
                                 - m2['is_buffer'] + m1['is_buffer'])
                        # 제약: 모험단 중복 없고, 버퍼 1~2명 유지
                        if (m2['adventure'] in adv_i or m1['adventure'] in adv_j or
                            buf_i < 1 or buf_i > 2 or buf_j < 1 or buf_j > 2):
                            continue
                        new_i = [m2 if m is m1 else m for m in parties[i]['members']]
                        new_j = [m1 if m is m2 else m for m in parties[j]['members']]
                        s_i = compute_party_score(new_i)
                        s_j = compute_party_score(new_j)
                        cand = scores.copy()
                        cand[i], cand[j] = s_i, s_j
                        new_std = stdev(cand) if len(cand) > 1 else 0.0
                        if new_std < curr_std:
                            curr_std, best_swap = new_std, (i, j, m1, m2)
        if not best_swap:
            break
        i, j, m1, m2 = best_swap
        parties[i]['members'].remove(m1); parties[i]['members'].append(m2)
        parties[j]['members'].remove(m2); parties[j]['members'].append(m1)
        parties[i]['adventures'] = {m['adventure'] for m in parties[i]['members']}
        parties[j]['adventures'] = {m['adventure'] for m in parties[j]['members']}

    # 8) 최종 통계 계산 및 반환
    final_scores = [compute_party_score(p['members']) for p in parties]
    score_range = max(final_scores) - min(final_scores)
    std_dev = stdev(final_scores) if len(final_scores) > 1 else 0.0
    party_lists = [p['members'] for p in parties]

    return party_lists, leftover, final_scores, score_range, std_dev



# 파티 결과를 DB 포맷으로 변환
def wrap_create_parties_alternative(buffers, dealers):
    charlist = adapt_characters(buffers) + adapt_characters(dealers)
    # assign_parties는 (List[List[dict]], leftover, scores, score_range, std_dev) 반환
    parties, leftover, scores, score_range, std_dev = assign_parties(charlist)
    result_parties = []

    # ★ 변경: 변수명을 party → member_list 로 변경하고,
    #          party["members"] 대신 member_list 자체를 사용합니다.
    for member_list, score in zip(parties, scores):  # ← 변경됨
        # party["members"] → member_list
        members = sorted(member_list, key=lambda x: x["score"], reverse=True)  # ← 변경됨

        # 기존 로직 그대로
        main_buf = next((m for m in members if m["is_buffer"]), None)
        others   = [m for m in members if m is not main_buf]
        dealer_list = others[:3]

        def recover(m):
            return {
                "adventure": m["account"],
                "chara_name": m["name"],
                "job": m["job"],
                "fame": m["fame"],
                "score": m["score"],
                "isbuffer": int(m["is_buffer"])
            }

        result_parties.append({
            "buffers":     [recover(main_buf)] if main_buf else [],
            "dealers":     [recover(m) for m in dealer_list],
            "party_score": score
        })

    unassigned = [
        {
            "adventure": m["account"],
            "chara_name": m["name"],
            "job":        m["job"],
            "fame":       m["fame"],
            "score":      m["score"],
            "isbuffer":   int(m["is_buffer"])
        }
        for m in leftover
    ]
    skipped = []
    return result_parties, unassigned, skipped


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Generate parties and insert into DB')
    parser.add_argument('role', nargs='?', choices=['temple','azure','venus','tmp'], default=None)
    args = parser.parse_args()

    base = os.path.dirname(os.path.abspath(__file__)) + '/..'
    db_path = os.path.join(base, 'database', 'DB.sqlite')

    buf_df, del_df = load_characters(db_path, args.role)
    buffers = buf_df.to_dict('records')
    dealers = del_df.to_dict('records')
    parties, unassigned, skipped = wrap_create_parties_alternative(buffers, dealers)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    tval = args.role or 'all'
    cur.execute("DELETE FROM party WHERE type = ?", (tval,))
    cur.execute("DELETE FROM abandonment WHERE type = ?", (tval,))
    for p in parties:
        buf = p['buffers'][0] if p['buffers'] else None
        buf_j = json.dumps({k: buf[k] for k in ('adventure','chara_name','job','fame','score')} | {'isbuffer': buf['isbuffer']}, ensure_ascii=False) if buf else ''
        dj = [json.dumps({k: d[k] for k in ('adventure','chara_name','job','fame','score')} | {'isbuffer': d['isbuffer']}, ensure_ascii=False) for d in p['dealers'][:3]]
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
