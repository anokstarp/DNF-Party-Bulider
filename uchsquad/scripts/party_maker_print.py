#!/usr/bin/env python3
import sys
import sqlite3
import pandas as pd
import os
import argparse
import json
import math
from collections import Counter

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


# DB에서 캐릭터 불러오기
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


def compute_party_score(members):
    # 파티 점수 공식 (사용하던 방식 유지)
    buffers = [m for m in members if m['is_buffer']]
    dealers = [m for m in members if not m['is_buffer']]
    main_buff = max(buffers, key=lambda x: x['score']) if buffers else None
    sub_buff = max([b for b in buffers if b != main_buff], key=lambda x: x['score']) if buffers and len(buffers) > 1 else None

    buff_factor = (main_buff['score'] / 3_000_000) if main_buff else 1.0
    dealer_sum = sum(d['score'] // 10_000_000 for d in dealers)
    sub_buff_factor = 1.0
    if sub_buff:
        sub_buff_factor = 1 + (sub_buff['score'] / 1_200_000) * 0.08
    return buff_factor * dealer_sum * sub_buff_factor

# assign_parties 함수 중, swap 및 leftover 보정 루프만 부분 교체

def assign_parties(characters):
    # 입력: 캐릭터 딕셔너리 목록 (is_buffer, score, adventure, chara_name 포함)
    # 1) account->adventure, name->chara_name 정규화
    for c in characters:
        if "account" in c and "adventure" not in c:
            c["adventure"] = c["account"]
        if "name" in c and "chara_name" not in c:
            c["chara_name"] = c["name"]

    from collections import defaultdict

    # 2) 파티 수 결정
    total = len(characters)
    adv_counts = Counter(ch['adventure'] for ch in characters)
    M_max = max(adv_counts.values()) if adv_counts else 0
    P_needed = total // 4
    buffers = [ch for ch in characters if ch['is_buffer']]
    P = min(P_needed, len(buffers))
    if P == 0:
        return [], characters[:], [], 0.0, 0.0

    # 3) 파티 초기화
    parties = [{'members': [], 'adventures': set()} for _ in range(P)]
    assigned = set()

    # 4) 모험단별 그룹화 및 정렬
    groups = defaultdict(list)
    for c in characters:
        groups[c['adventure']].append(c)
    adventures = sorted(groups.keys(), key=lambda adv: len(groups[adv]), reverse=True)

    # 5) 그룹 순서대로 배치
    for idx_adv, adv in enumerate(adventures):
        group = groups[adv]
        # 짝수 인덱스: 내림차순, 홀수: 오름차순
        reverse = (idx_adv % 2 == 0)
        sorted_group = sorted(group, key=lambda x: x['score'], reverse=reverse)
        for char in sorted_group:
            # 버퍼/딜러 슬롯 규칙에 따라 후보 파티 찾기
            if char['is_buffer']:
                # 버퍼 없는 파티 우선
                cands = [i for i, p in enumerate(parties)
                         if len(p['members']) < 4
                         and adv not in p['adventures']
                         and sum(m['is_buffer'] for m in p['members']) == 0]
                # 모두 버퍼 있으면 빈 슬롯만 체크
                if not cands and all(sum(m['is_buffer'] for m in p['members']) > 0 for p in parties):
                    cands = [i for i, p in enumerate(parties)
                             if len(p['members']) < 4 and adv not in p['adventures']]
            else:
                cands = [i for i, p in enumerate(parties)
                         if len(p['members']) < 4 and adv not in p['adventures']]
            if not cands:
                continue
            # 최소 멤버 수, 파티 점수 기준으로 선택
            scores = [compute_party_score(p['members']) for p in parties]
            sel = min(cands, key=lambda i: (len(parties[i]['members']), scores[i]))
            parties[sel]['members'].append(char)
            parties[sel]['adventures'].add(adv)
            assigned.add((char['adventure'], char['chara_name']))

    # 6) leftover 계산
    leftover = [c for c in characters if (c['adventure'], c['chara_name']) not in assigned]

    # 7) 내부 스왑 기반 균형 보정 (최대 100회)
    def std(scores):
        avg = sum(scores) / len(scores)
        return math.sqrt(sum((s - avg) ** 2 for s in scores) / len(scores)) if len(scores) > 1 else 0.0

    for _ in range(100):
        party_scores = [compute_party_score(p['members']) for p in parties]
        best_std = std(party_scores)
        best_swap = None
        for i in range(P):
            for j in range(i+1, P):
                for m1 in parties[i]['members']:
                    for m2 in parties[j]['members']:
                        # 모험단 중복
                        if m2['adventure'] in {m['adventure'] for m in parties[i]['members'] if m!=m1}: continue
                        if m1['adventure'] in {m['adventure'] for m in parties[j]['members'] if m!=m2}: continue
                        # 버퍼 최소 1명 보장
                        if sum(m['is_buffer'] for m in parties[i]['members']) - m1['is_buffer'] + m2['is_buffer'] < 1: continue
                        if sum(m['is_buffer'] for m in parties[j]['members']) - m2['is_buffer'] + m1['is_buffer'] < 1: continue
                        # 인원 제한
                        if len(parties[i]['members']) > 4 or len(parties[j]['members']) > 4: continue
                        # 시뮬 swap
                        new_i = [m if m!=m1 else m2 for m in parties[i]['members']]
                        new_j = [m if m!=m2 else m1 for m in parties[j]['members']]
                        sc_i = compute_party_score(new_i)
                        sc_j = compute_party_score(new_j)
                        cand = party_scores.copy()
                        cand[i], cand[j] = sc_i, sc_j
                        new_std = std(cand)
                        if new_std < best_std:
                            best_std, best_swap = new_std, (i, j, m1, m2)
        if not best_swap:
            break
        i, j, m1, m2 = best_swap
        parties[i]['members'].remove(m1)
        parties[i]['members'].append(m2)
        parties[j]['members'].remove(m2)
        parties[j]['members'].append(m1)
        parties[i]['adventures'] = {m['adventure'] for m in parties[i]['members']}
        parties[j]['adventures'] = {m['adventure'] for m in parties[j]['members']}

    # 8) 최종 통계
    final_scores = [compute_party_score(p['members']) for p in parties]
    score_range = max(final_scores) - min(final_scores) if final_scores else 0.0
    std_dev = std(final_scores)
    return parties, leftover, final_scores, score_range, std_dev



# 파티 결과를 DB 포맷으로 변환
def wrap_create_parties_alternative(buffers, dealers):
    charlist = adapt_characters(buffers) + adapt_characters(dealers)
    parties, leftover, scores, score_range, std_dev = assign_parties(charlist)
    result_parties = []
    for party, score in zip(parties, scores):
        # 파티 멤버 4명을 점수 내림차순(혹은 이미 배치 순서)으로 가져오기
        members = sorted(party["members"], key=lambda x: x["score"], reverse=True)
        # is_buffer=1인 버퍼 중 제일 점수 높은 1명만 buffer 자리에!
        main_buf = next((m for m in members if m["is_buffer"]), None)
        other_members = [m for m in members if m != main_buf]
        # 나머지 3명을 딜러로 배정 (여기엔 is_buffer=1 버퍼도 들어갈 수 있음!)
        dealer_list = other_members[:3]  # 3명까지
        def recover_one(m):
            return {
                "adventure": m["account"],
                "chara_name": m["name"],
                "job": m["job"],
                "fame": m["fame"],
                "score": m["score"],
                "isbuffer": int(m["is_buffer"]),
            }
        result_parties.append({
            "buffers": [recover_one(main_buf)] if main_buf else [],
            "dealers": [recover_one(m) for m in dealer_list],
            "party_score": score,
        })
    def recover_one(m):
        return {
            "adventure": m["account"],
            "chara_name": m["name"],
            "job": m["job"],
            "fame": m["fame"],
            "score": m["score"],
            "isbuffer": int(m["is_buffer"]),
        }
    unassigned = [recover_one(m) for m in leftover]
    skipped = []
    return result_parties, unassigned, skipped




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

    # 포인트 계산 없이 raw dict로 바로 파티 생성에 사용
    buffers = buf_df.to_dict('records')
    dealers = del_df.to_dict('records')
    parties, unassigned, skipped = wrap_create_parties_alternative(buffers, dealers)

    print(f"Loaded: total={len(buffers)+len(dealers)} (buffers={len(buffers)}, dealers={len(dealers)})\n")
    for i, p in enumerate(parties, 1):
        if p['buffers']:
            b = p['buffers'][0]
            print(f"Party {i}: Buffer: {b['adventure']}—{b['chara_name']}({b['score']:,})")
        else:
            print(f"Party {i}: Buffer: None")
        for j, d in enumerate(p['dealers'], 1): print(f"  Dealer{j}: {d['adventure']}—{d['chara_name']}({d['score']:,})")
        print(f"  Combined: {p['party_score']:.2f}\n")

    print("=== Unassigned ===")
    for c in unassigned:
        role_lbl = "버퍼" if c['isbuffer'] == 1 else "딜러"
        print(f"[{role_lbl}] {c['adventure']}—{c['chara_name']}({c['score']:,})")
    print(f"총 {len(unassigned)}명 남음\n")

    # DB 저장
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    tval = args.role or 'all'
    cur.execute("DELETE FROM party WHERE type = ?", (tval,))
    cur.execute("DELETE FROM abandonment WHERE type = ?", (tval,))
    for p in parties:
        if p['buffers']:
            buf = p['buffers'][0]
            buf_j = json.dumps({k: buf[k] for k in ('adventure','chara_name','job','fame','score')} | {'isbuffer': buf['isbuffer']}, ensure_ascii=False)
        else:
            buf_j = ''
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
    print(f"→ DB에 {len(parties)}개 파티와 {len(unassigned)}명 남은 캐릭터 저장 완료 (type={tval})")
