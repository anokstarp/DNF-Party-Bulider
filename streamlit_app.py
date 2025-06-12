import streamlit as st
import pandas as pd
import random
import statistics
from itertools import combinations

# ---------------------------------------------
# 1) 데이터 프리셋 정의
# 필요한 만큼 프리셋을 추가하세요.
PRESETS = {
    "프리셋 1": [
        # 기본 데이터셋
        ("찬호","크루",500),("찬호","뮤즈",428),("찬호","꼬홀",313),("찬호","메딕",304),
        ("범규","크루",382),("범규","뮤즈",344),("범규","메딕",301),
        ("남석","크루",439),("남석","메딕",408),
        ("종현","크루",435),("종현","크루2",285),("종현","메딕",302),
        ("찬호","스커",61.1),("찬호","넨마",37.4),("찬호","카오스",22.9),
        ("찬호","블레",21.7),("찬호","스핏",18.8),("찬호","버서커",11.4),
        ("찬호","스위프트",8.1),("찬호","키메라",9.6),
        ("범규","아수라",29.1),("범규","소환사",25.3),("범규","미스트",23.1),
        ("범규","버서커",22.9),("범규","베매",15.3),("범규","넨마",14.2),
        ("범규","키메라",14.5),("범규","데슬",9.3),("범규","스위프트",4.9),
        ("남석","버서커",61.5),("남석","마도",35.5),("남석","스커",16.3),
        ("남석","데슬",9.6),("남석","사령",8.5),("남석","런처",5.6),
        ("종현","그플",29.2),("종현","이단",12.5),("종현","팔라딘",22.3),
        ("종현","키메라",10),("종현","닼템",3.4),
        ("현수","로제",45),("현수","스커",30.7),("현수","넨마",58),
        ("현수","카오스",54.6),("현수","메딕",3),
        ("경베","뮤즈",2),("경베","배메",2),("경베","블레",2)
    ],
    "프리셋 2": [
        # 예시: 다른 데이터셋
        ("A","버퍼",320),("B","버퍼",280),("C","버퍼",350),
        ("X","딜러",50),("Y","딜러",60),("Z","딜러",70),
        ("D","딜러",45),("E","딜러",55),("F","딜러",65),
        ("G","딜러",40),("H","딜러",35),("I","딜러",25)
    ]
}

# ---------------------------------------------
# 2) 파티 구성 알고리즘

def make_parties(data):
    # 버퍼·딜러 분류
    buffers = [{"player":p,"job":j,"power":pw} for p,j,pw in data if pw >= 100]
    dealers = [{"player":p,"job":j,"power":pw} for p,j,pw in data if pw < 100]
    n = len(buffers)

    # 딜러 부족 체크
    if len(dealers) < n * 3:
        st.error(f"필요한 딜러: {n*3}, 현재 딜러: {len(dealers)}. 딜러가 부족합니다.")
        return None, None

    # 백트래킹 초기 배치
    used = [False] * len(dealers)
    assign = [None] * n

    def backtrack(idx):
        if idx == n:
            return True
        buf = buffers[idx]
        candidates = [i for i, d in enumerate(dealers)
                      if not used[i] and d["player"] != buf["player"]]
        for combo in combinations(candidates, 3):
            if len({dealers[i]["player"] for i in combo}) != 3:
                continue
            for i in combo: used[i] = True
            assign[idx] = combo
            if backtrack(idx+1): return True
            for i in combo: used[i] = False
        return False

    backtrack(0)

    # 파티 배열 생성
    parties = []
    for i, buf in enumerate(buffers):
        party = {"buffer": buf, "dealers": [dealers[x] for x in assign[i]]}
        parties.append(party)

    # 힐 클라이밍으로 균등화
    def party_damage(p):
        return sum(d["power"] for d in p["dealers"]) * (p["buffer"]["power"]/300)
    best_std = statistics.pstdev([party_damage(p) for p in parties])
    improving = True
    while improving:
        improving = False
        for a in range(n):
            for b in range(a+1, n):
                for ai in range(3):
                    for bi in range(3):
                        A, B = parties[a], parties[b]
                        da, db = A["dealers"][ai], B["dealers"][bi]
                        # 스왑 후보
                        newA = [x for x in A["dealers"] if x is not da] + [db]
                        newB = [x for x in B["dealers"] if x is not db] + [da]
                        # 중복 플레이어 체크
                        if len({A["buffer"]["player"]} | {d["player"] for d in newA}) != 4: continue
                        if len({B["buffer"]["player"]} | {d["player"] for d in newB}) != 4: continue
                        # 적용 및 평가
                        origA, origB = A["dealers"][ai], B["dealers"][bi]
                        A["dealers"][ai], B["dealers"][bi] = db, da
                        new_std = statistics.pstdev([party_damage(p) for p in parties])
                        if new_std < best_std:
                            best_std = new_std
                            improving = True
                        else:
                            A["dealers"][ai], B["dealers"][bi] = origA, origB
    return parties, best_std

# ---------------------------------------------
# 3) Streamlit UI
st.title("🎮 던파 파티 구성 도구")

preset_name = st.sidebar.selectbox("■ 프리셋 선택", list(PRESETS.keys()))
if st.sidebar.button("▶ 구성 실행"):
    data = PRESETS[preset_name]
    parties, std = make_parties(data)
    if parties is None:
        st.stop()
    # 결과 테이블 생성
    rows = []
    for pid, p in enumerate(parties, 1):
        dmg = sum(d["power"] for d in p["dealers"]) * (p["buffer"]["power"]/300)
        rows.append({"파티": pid, "역할": "버퍼", "플레이어": p["buffer"]["player"],
                     "직업군": p["buffer"]["job"], "전투력": p["buffer"]["power"], "파티딜량": round(dmg,2)})
        for d in p["dealers"]:
            rows.append({"파티": pid, "역할": "딜러", "플레이어": d["player"],
                         "직업군": d["job"], "전투력": d["power"], "파티딜량": ""})
    df = pd.DataFrame(rows)
    st.markdown(f"### [{preset_name}] 최종 표준편차: {std:.2f}")
    st.dataframe(df, use_container_width=True)
