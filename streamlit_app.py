import streamlit as st
import pandas as pd
import random
import statistics
from itertools import combinations

XCLUDE_PAIRS = [
    ("경베", "현수"),
    
]


# ---------------------------------------------
# 1) 데이터 프리셋 정의

dundamData = subprocess.check_output(
    ['python', 'dundamCrawler.py'],
    text=True
)

PRESETS = {
    "베누스": [
        ("찬호","크루",500),
        ("찬호","뮤즈",428),
        ("찬호","꼬홀",313),
        ("찬호","메딕",304),
        ("범규","크루",382),
        ("범규","뮤즈",344),
        ("범규","메딕",301),
        ("남석","크루",439),
        ("남석","메딕",408),
        ("종현","크루",435),
        ("종현","크루2",285),
        ("종현","메딕",302),
        ("찬호","스커",61.1),
        ("찬호","넨마",37.4),
        ("찬호","카오스",22.9),
        ("찬호","블레",21.7),
        ("찬호","스핏",18.8),
        ("찬호","버서커",11.4),
        ("찬호","스위프트",8.1),
        ("찬호","키메라",9.6),
        ("범규","아수라",29.1),
        ("범규","소환사",25.3),
        ("범규","미스트",23.1),
        ("범규","버서커",22.9),
        ("범규","베매",15.3),
        ("범규","넨마",14.2),
        ("범규","키메라",14.5),
        ("범규","데슬",9.3),
        ("범규","스위프트",4.9),
        ("남석","버서커",61.5),
        ("남석","마도",35.5),
        ("남석","스커",16.3),
        ("남석","데슬",9.6),
        ("남석","사령",8.5),
        ("남석","런처",5.6),
        ("종현","그플",29.2),
        ("종현","이단",12.5),
        ("종현","팔라딘",22.3),
        ("종현","키메라",10),
        ("종현","닼템",3.4),
        ("현수","로제",45),
        ("현수","스커",30.7),
        ("현수","넨마",58),
        ("현수","카오스",54.6),
        ("현수","메딕",3),
        ("경베","뮤즈",2),
        ("경베","배메",2),
        ("경베","블레",2)
    ],
    "여신전": [
        ("찬호","크루",500),
        ("찬호","꼬홀",313),
        ("찬호","메딕",304),
        ("범규","크루",382),
        ("범규","인챈",255),
        ("범규","메딕",301),
        ("남석","크루",439),
        ("남석","메딕",408),
        ("종현","크루",435),
        ("종현","크루2",6),
        ("종현","메딕",302),
        ("현수","크루2",6),  
        ("찬호","웨펀",76.2),
        ("찬호","카오스",22.9),
        ("찬호","블레",21.7),
        ("찬호","스핏",18.8),
        ("찬호","버서커",11.4),
        ("찬호","스위프트",8.1),
        ("찬호","키메라",9.6),
        ("범규","아수라",29.1),
        ("범규","소환사",25.3),
        ("범규","버서커",22.9),
        ("범규","미스트",23.1),
        ("범규","넨마",14.2),
        ("범규","키메라",14.5),
        ("범규","데슬",9.3),
        ("남석","버서커",61.5),
        ("남석","마도",35.5),
        ("남석","스커",16.3),
        ("남석","데슬",9.6),
        ("남석","사령",8.5),
        ("남석","런처",5.6),
        ("종현","그플",29.2),
        ("종현","이단",12.5),
        ("종현","팔라딘",22.3),
        ("종현","키메라",10),
        ("현수","로제",45),
        ("현수","스커",30.7),
        ("현수","넨마",58),
        ("현수","카오스",54.6)
        
    ],
    "애쥬어": [
        ("찬호","메딕",304),
        ("범규","인챈",255),
        ("범규","메딕",301),
        ("종현","크루2",285),
        ("종현","메딕",302),
        ("현수","크루2",285),
        ("찬호","카오스",22.9),
        ("찬호","블레",21.7),
        ("찬호","스핏",18.8),
        ("찬호","스위프트",8.1),
        ("찬호","키메라",9.6),
        ("범규","버서커",22.9),
        ("범규","넨마",14.2),
        ("범규","키메라",14.5),
        ("범규","데슬",9.3),
        ("남석","스커",16.3),
        ("남석","데슬",9.6),
        ("남석","사령",8.5),
        ("남석","런처",5.6),
        ("종현","키메라",10),
        ("현수","로제",45),
        ("현수","스커",30.7),
        ("현수","넨마",58),
        ("현수","카오스",54.6)
        
        ]
    
}

# 여기 주석 처리하면 기존 프리셋 사용
PRESETS = ast.literal_eval(dundamData)

# ---------------------------------------------
# 2) 파티 구성 알고리즘
def make_parties(data):
    buffers = [{"player":p,"job":j,"power":pw} for p,j,pw in data if pw >= 100]
    dealers = [{"player":p,"job":j,"power":pw} for p,j,pw in data if pw < 100]
    n = len(buffers)
    if len(dealers) < n * 3:
        st.error(f"필요한 딜러: {n*3}, 현재 딜러: {len(dealers)}. 딜러가 부족합니다.")
        return None, None

    # 비허용 쌍을 set 집합으로
    exclude_sets = [set(pair) for pair in XCLUDE_PAIRS]

    used = [False] * len(dealers)
    assign = [None] * n

    def backtrack(idx):
        if idx == n:
            return True
        buf = buffers[idx]
        candidates = [i for i, d in enumerate(dealers)
                      if not used[i] and d["player"] != buf["player"]]
        for combo in combinations(candidates, 3):
            # 파티 플레이어 집합
            party_players = {buf["player"]} | {dealers[i]["player"] for i in combo}
            # ① 플레이어 중복 체크 (버퍼≠딜러, 딜러간 서로 다른 유저)
            if len(party_players) != 4:
                continue
            # ② 비허용 쌍 체크
            if any(excl.issubset(party_players) for excl in exclude_sets):
                continue

            # 허용된 조합이면 사용 처리
            for i in combo:
                used[i] = True
            assign[idx] = combo
            if backtrack(idx + 1):
                return True
            # 되돌리기
            for i in combo:
                used[i] = False
        return False

    success = backtrack(0)
    if not success:
        return None, None

    # 초기 파티 목록 생성
    parties = []
    for i, buf in enumerate(buffers):
        parties.append({"buffer": buf,
                        "dealers": [dealers[x] for x in assign[i]]})

    # 파티딜량 계산 함수
    def party_damage(p):
        return sum(d["power"] for d in p["dealers"]) * (p["buffer"]["power"]/300)

    # 힐 클라이밍 단계에서도 스왑 후 비허용 쌍 검사 추가
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
                        # 스왑 후 새로운 파티원 집합
                        newA = [d for d in A["dealers"] if d is not da] + [db]
                        newB = [d for d in B["dealers"] if d is not db] + [da]
                        # 플레이어 집합
                        setA = {A["buffer"]["player"]} | {d["player"] for d in newA}
                        setB = {B["buffer"]["player"]} | {d["player"] for d in newB}
                        # 중복/비허용 쌍 체크
                        if len(setA)!=4 or len(setB)!=4:
                            continue
                        if any(excl.issubset(setA) for excl in exclude_sets):
                            continue
                        if any(excl.issubset(setB) for excl in exclude_sets):
                            continue
                        # 시도 및 평가
                        origA, origB = da, db
                        A["dealers"][ai], B["dealers"][bi] = db, da
                        new_std = statistics.pstdev([party_damage(p) for p in parties])
                        if new_std < best_std:
                            best_std = new_std
                            improving = True
                        else:
                            A["dealers"][ai], B["dealers"][bi] = origA, origB

    return parties, best_std

# 3) Streamlit UI (표 형태 + 플레이어별 색상)
st.title("🎮 던파 파티 구성 도구")
st.sidebar.write("### 데이터 프리셋 선택")
preset_name = st.sidebar.selectbox("", list(PRESETS.keys()))
if st.sidebar.button("🚀 구성 실행"):
    data = PRESETS[preset_name]
    parties, std = make_parties(data)
    if parties is None:
        st.error("유효한 파티 구성을 찾을 수 없습니다.")
        st.stop()

    st.markdown(f"## {preset_name}")
    st.markdown(f"**최종 표준편차:** {std:.2f}")

    # 1) 플레이어별 고유 색 맵 생성 (원하는 색으로 바꿔도 OK)
    all_players = sorted({d['player'] for p in parties for d in ([p['buffer']] + p['dealers'])})
    palette = ["#FFCCCC", "#CCFFCC", "#CCCCFF", "#FFFFCC", "#FFCCFF", "#CCFFFF"]
    color_map = {pl: palette[i % len(palette)] for i, pl in enumerate(all_players)}

    # 2) 파티별로 DataFrame 만들고 스타일 적용
    for idx, p in enumerate(parties, start=1):
        # 테이블용 리스트
        rows = []
        dmg = sum(d["power"] for d in p["dealers"]) * (p["buffer"]["power"]/300)
        rows.append({
            "역할": "버퍼",
            "플레이어": p["buffer"]["player"],
            "직업군": p["buffer"]["job"],
            "전투력": round(p["buffer"]["power"],1),
            "파티딜량": round(dmg,2)
        })
        for d in p["dealers"]:
            rows.append({
                "역할": "딜러",
                "플레이어": d["player"],
                "직업군": d["job"],
                "전투력": round(d["power"],1),
                "파티딜량": ""
            })
        df = pd.DataFrame(rows).reset_index(drop=True)

        # 플레이어별 고유 색 맵 (같은 코드 재사용)
        def highlight_player(val):
            return f"background-color: {color_map.get(val)}" if val in color_map else ""

        styled = (
            df.style
              # 플레이어 컬럼만 색 입히기
              .applymap(highlight_player, subset=["플레이어"])
              # 테두리·정렬 설정
              .set_properties(**{"border": "1px solid #ddd", "text-align": "center"})
              # 인덱스 숨기기(CSS)
              .set_table_styles([
                  {"selector": "th.row_heading, td.row_heading", "props": [("display", "none")]},
              ])
        )

        st.markdown(f"### 파티 {idx}")
        st.dataframe(styled, use_container_width=True)
        st.markdown("---")

