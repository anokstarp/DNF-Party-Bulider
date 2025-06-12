import streamlit as st
import pandas as pd
import random, statistics
from itertools import combinations

PRESETS = {
    "베누스": [
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
    
}

def make_parties(data):
    buffers = [{"player":p,"job":j,"power":pw} for p,j,pw in data if pw>=100]
    dealers = [{"player":p,"job":j,"power":pw} for p,j,pw in data if pw<100]

    n = len(buffers)
    used = [False]*len(dealers)
    assign = [None]*n
    def backtrack(i):
        if i==n: return True
        buf = buffers[i]
        avail = [idx for idx,d in enumerate(dealers)
                 if not used[idx] and d["player"]!=buf["player"]]
        for combo in combinations(avail, 3):
            if len({dealers[x]["player"] for x in combo})!=3: continue
            for x in combo: used[x]=True
            assign[i]=combo
            if backtrack(i+1): return True
            for x in combo: used[x]=False
        return False

    backtrack(0)
    rows=[]
    for pid, buf in enumerate(buffers,1):
        rows.append([pid,"버퍼",buf["player"],buf["job"],buf["power"]])
        for di in assign[pid-1]:
            d=dealers[di]
            rows.append([pid,"딜러",d["player"],d["job"],d["power"]])
    return pd.DataFrame(rows, columns=["파티","역할","플레이어","직업군","전투력"])

st.title("파티 구성 데모")
preset = st.sidebar.selectbox("▶ 프리셋 선택", list(PRESETS.keys()))
if st.sidebar.button("🚀 실행"):
    df = make_parties(PRESETS[preset])
    st.markdown(f"### [{preset}] 결과")
    st.dataframe(df, use_container_width=True)
