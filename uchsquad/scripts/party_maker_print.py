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
        sub_buff_factor = 1 + (sub_buff['score'] / 1_000_000) * 0.08
    return buff_factor * dealer_sum * sub_buff_factor

def assign_parties(characters):
    # 입력: 캐릭터 딕셔너리 목록
    # account -> adventure, name -> chara_name 정규화
    for c in characters:
        if "account" in c and "adventure" not in c:
            c["adventure"] = c["account"]
        if "name" in c and "chara_name" not in c:
            c["chara_name"] = c["name"]

    buffers = [ch for ch in characters if ch['is_buffer']]
    dps = [ch for ch in characters if not ch['is_buffer']]
    B = len(buffers)
    total = len(characters)
    # 모험단별 인원수 집계
    adv_counts = Counter(ch['adventure'] for ch in characters)
    M_max = max(adv_counts.values()) if adv_counts else 0

    # 파티수 결정
    P_needed = math.ceil(total / 4)
    P = max(P_needed, M_max)
    P = min(P, B)  # 버퍼 수 만큼만 파티 생성 가능
    if P == 0:
        return [], characters[:], [], 0.0, 0.0

    # 파티 리스트 초기화
    parties = [{'members': [], 'adventures': set()} for _ in range(P)]
    party_scores = [0] * P

    # 버퍼 점수 순 정렬 후 각 파티에 1명씩 우선 배치
    buffers_sorted = sorted(buffers, key=lambda x: x['score'], reverse=True)
    assigned = set()
    for i in range(P):
        buf = buffers_sorted[i]
        parties[i]['members'].append(buf)
        parties[i]['adventures'].add(buf['adventure'])
        assigned.add((buf['adventure'], buf['chara_name']))
        party_scores[i] += buf['score']

    # 남는 버퍼와 딜러 합쳐 점수 내림차순 정렬
    extra_buffers = buffers_sorted[P:]
    remaining_chars = sorted(extra_buffers + dps, key=lambda x: x['score'], reverse=True)

    # 점수 낮은 파티부터 조건 맞는 곳에 분배
    for char in remaining_chars:
        candidates = []
        for idx in range(P):
            party = parties[idx]
            if len(party['members']) >= 4:
                continue
            if char['adventure'] in party['adventures']:
                continue
            candidates.append((party_scores[idx], idx))
        if candidates:
            # 점수 낮은 파티 우선
            _, sel = min(candidates)
            parties[sel]['members'].append(char)
            parties[sel]['adventures'].add(char['adventure'])
            assigned.add((char['adventure'], char['chara_name']))
            party_scores[sel] += char['score']

    # 할당 안된 캐릭터는 leftover
    leftover = [c for c in characters if (c['adventure'], c['chara_name']) not in assigned]

    # --- 편차 최소화: 파티간 반복 교환 (swap) ---
    max_iter = 500
    improved = True
    iter_count = 0

    def get_std(scores):
        avg = sum(scores) / len(scores)
        return math.sqrt(sum((s - avg) ** 2 for s in scores) / len(scores)) if len(scores) > 1 else 0.0

    while improved and iter_count < max_iter:
        improved = False
        iter_count += 1
        # 현재 각 파티 점수
        party_scores = [compute_party_score(p['members']) for p in parties]
        avg_score = sum(party_scores) / len(party_scores)
        std = get_std(party_scores)
        best_swap = None
        best_std = std
        # 파티 쌍 순회
        for i in range(P):
            for j in range(P):
                if i == j:
                    continue
                for m1 in parties[i]['members']:
                    for m2 in parties[j]['members']:
                        # 같은 모험단이 상대파티에 이미 있으면 skip
                        if m2['adventure'] in [m['adventure'] for m in parties[i]['members'] if m != m1]:
                            continue
                        if m1['adventure'] in [m['adventure'] for m in parties[j]['members'] if m != m2]:
                            continue
                        # 버퍼 조건
                        i_buf_cnt = sum(m['is_buffer'] for m in parties[i]['members'])
                        j_buf_cnt = sum(m['is_buffer'] for m in parties[j]['members'])
                        i_buf_next = i_buf_cnt - m1['is_buffer'] + m2['is_buffer']
                        j_buf_next = j_buf_cnt - m2['is_buffer'] + m1['is_buffer']
                        if i_buf_next < 1 or j_buf_next < 1:
                            continue
                        # 인원 제한
                        if len(parties[i]['members']) > 4 or len(parties[j]['members']) > 4:
                            continue
                        # swap 시뮬
                        new_i_members = [m for m in parties[i]['members'] if m != m1] + [m2]
                        new_j_members = [m for m in parties[j]['members'] if m != m2] + [m1]
                        new_scores = party_scores[:]
                        new_scores[i] = compute_party_score(new_i_members)
                        new_scores[j] = compute_party_score(new_j_members)
                        new_std = get_std(new_scores)
                        if new_std < best_std - 1e-3:  # 유의미하게 줄어들면
                            best_std = new_std
                            best_swap = (i, j, m1, m2)
        if best_swap:
            i, j, m1, m2 = best_swap
            parties[i]['members'].remove(m1)
            parties[j]['members'].remove(m2)
            parties[i]['members'].append(m2)
            parties[j]['members'].append(m1)
            parties[i]['adventures'] = set(m['adventure'] for m in parties[i]['members'])
            parties[j]['adventures'] = set(m['adventure'] for m in parties[j]['members'])
            improved = True

    

    # leftover 최종 보정 루프
    prev_leftover_sets = set()
    change = True
    while change and leftover:
        # 반복 leftover 명단이면 루프 종료 (무한루프 방지)
        leftover_ids = frozenset((c['adventure'], c['chara_name']) for c in leftover)
        if leftover_ids in prev_leftover_sets:
            break
        prev_leftover_sets.add(leftover_ids)
        
        change = False
        new_leftover = []
        for char in leftover:
            inserted = False
            # 1. 우선 빈 자리가 있는 파티가 있다면 (기존 코드가 처리했다면 패스)
            # 2. 이미 4명인 파티에도 '내보낼 멤버'와 교환할 수 있다면 swap
            for pi, party in enumerate(parties):
                # 4명 꽉찬 파티만 고려
                if len(party['members']) < 4:
                    continue
                if char['adventure'] in party['adventures']:
                    continue
                # 버퍼조건: char이 버퍼면, 내보내는 멤버가 버퍼여도 되고 딜러여도 됨(단, 버퍼가 한 명 뿐인 파티에서 버퍼를 내보낼 순 없음)
                # char이 딜러면, 반드시 내보내는 멤버가 딜러여야 함 (버퍼 한 명밖에 없는 파티에서 버퍼 내보내면 안 되므로)
                candidate_idx = None
                min_score = float('inf')
                for idx, m in enumerate(party['members']):
                    # 내보내는 멤버가 char과 모험단 겹치면 skip (중복금지)
                    if m['adventure'] == char['adventure']:
                        continue
                    # 버퍼 조건 체크
                    if char['is_buffer'] == 0 and m['is_buffer'] == 1:
                        # char이 딜러인데 버퍼를 내보내면 버퍼가 부족할 수 있음
                        if sum(mem['is_buffer'] for mem in party['members']) == 1:
                            continue  # 버퍼 1명인 파티에서 버퍼 내보내면 불가
                    # 가장 점수 낮은 멤버 우선
                    if m['score'] < min_score:
                        candidate_idx = idx
                        min_score = m['score']
                if candidate_idx is not None:
                    # 교환 실행
                    old_member = party['members'][candidate_idx]
                    party['members'][candidate_idx] = char
                    party['adventures'] = set(m['adventure'] for m in party['members'])
                    # leftover 처리
                    new_leftover.append(old_member)
                    inserted = True
                    change = True
                    break  # char 처리됐으므로 다음 leftover 캐릭터로
            if not inserted:
                new_leftover.append(char)
        leftover = new_leftover


    # 최종 점수, 표준편차, 범위 계산
    final_scores = [compute_party_score(p['members']) for p in parties]
    score_range = max(final_scores) - min(final_scores) if final_scores else 0.0
    std_dev = get_std(final_scores)

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
            buf_j = json.dumps({k: buf[k] for k in ('adventure','chara_name','job','fame','score')}, ensure_ascii=False)
        else:
            buf_j = ''
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
