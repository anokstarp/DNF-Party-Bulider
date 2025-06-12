import streamlit as st
import pandas as pd
import random
import statistics
import subprocess, ast, sys
from itertools import combinations

# ---------------------------------------------
# 1) 외부 크롤러로부터 데이터 프리셋 로드
#    dundamCrawler.py 출력 형식: Python dict 문자열 형태의 PRESETS
try:
    # 현재 실행하는 파이썬 인터프리터로 크롤러 실행
    raw = subprocess.check_output(
        [sys.executable, "dundamCrawler.py"],
        text=True,
        stderr=subprocess.STDOUT
    )
    PRESETS = ast.literal_eval(raw)
except Exception as e:
    st.warning(f"크롤러 로드 실패({e!r}), 기본 프리셋으로 대체합니다.")
    # 최소 동작할 기본 프리셋
    PRESETS = {
        "기본 예시": [
            ("테스트","버퍼",300),("테스트","딜러1",10),
            ("테스트","딜러2",20),("테스트","딜러3",30),
        ]
    }

# ---------------------------------------------
# 2) 파티 구성 및 최적화 알고리즘

def make_parties(data):
    # 분류
    buffers = [{"player":p, "job":j, "power":pw} for p,j,pw in data if pw >= 100]
    dealers = [{"player":p, "job":j, "power":pw} for p,j,pw in data if pw < 100]
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
        avail = [i for i, d in enumerate(dealers)
                 if not used[i] and d["player"] != buf["player"]]
        for combo in combinations(avail, 3):
            if len({dealers[i]["player"] for i in combo}) != 3:
                continue
            for i in combo:
                used[i] = True
            assign[idx] = combo
            if backtrack(idx + 1):
                return True
            for i in combo:
                used[i] = False
        return False

    success = backtrack(0)
    if not success:
        st.error("❌ 유효한 파티 구성을 찾을 수 없습니다. 입력 데이터를 확인하세요.")
        return None, None

    # 파티 리스트 생성
    parties = []
    for i, buf in enumerate(buffers):
        party = {"buffer": buf, "dealers": [dealers[x] for x in assign[i]]}
        parties.append(party)

    # 파티딜량 계산 함수
    def party_damage(p):
        dealer_sum = sum(d["power"] for d in p["dealers"])
        return dealer_sum * (p["buffer"]["power"] / 300)

    # 힐 클라이밍: 표준편차 최소화
    best_std = statistics.pstdev([party_damage(p) for p in parties])
    improved = True
    while improved:
        improved = False
        for a in range(n):
            for b in range(a + 1, n):
                for i in range(3):
                    for j in range(3):
                        A, B = parties[a], parties[b]
                        da, db = A["dealers"][i], B["dealers"][j]
                        # 교체 후보 생성
                        newA = [d for d in A["dealers"] if d is not da] + [db]
                        newB = [d for d in B["dealers"] if d is not db] + [da]
                        # 중복 플레이어 검사
                        if len({A["buffer"]["player"]} | {d["player"] for d in newA}) != 4:
                            continue
                        if len({B["buffer"]["player"]} | {d["player"] for d in newB}) != 4:
                            continue
                        # 적용 후 평가
                        origA, origB = da, db
                        A["dealers"][i], B["dealers"][j] = db, da
                        new_std = statistics.pstdev([party_damage(p) for p in parties])
                        if new_std < best_std:
                            best_std = new_std
                            improved = True
                        else:
                            # 복원
                            A["dealers"][i], B["dealers"][j] = origA, origB
    return parties, best_std

# ---------------------------------------------
# 3) Streamlit UI
st.title("🎮 던파 파티 구성 도구")

if not PRESETS:
    st.warning("사용 가능한 데이터 프리셋이 없습니다.")
else:
    preset_name = st.sidebar.selectbox("■ 데이터 프리셋 선택", list(PRESETS.keys()))
    if st.sidebar.button("▶ 파티 구성 실행"):
        data = PRESETS[preset_name]
        parties, std = make_parties(data)
        if parties is None:
            st.stop()
            # 결과 테이블 준비
            rows = []
            for pid, p in enumerate(parties, 1):
                dmg = sum(d["power"] for d in p["dealers"]) * (p["buffer"]["power"] / 300)
                rows.append({"파티": pid, "역할": "버퍼", "플레이어": p["buffer"]["player"],
                             "직업군": p["buffer"]["job"], "전투력": p["buffer"]["power"],
                             "파티딜량": round(dmg, 2)})
                for d in p["dealers"]:
                    rows.append({"파티": pid, "역할": "딜러", "플레이어": d["player"],
                                 "직업군": d["job"], "전투력": d["power"], "파티딜량": ""})
            df = pd.DataFrame(rows)
            st.markdown(f"### [{preset_name}] 최종 표준편차: {std:.2f}")
            st.dataframe(df, use_container_width=True)
