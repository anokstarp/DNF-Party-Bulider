import streamlit as st
import pandas as pd
import random, statistics
import subprocess, ast
from itertools import combinations

dundamData = subprocess.check_output(
    ['python', 'dundamCrawler.py'],
    text=True
)

PRESETS = ast.literal_eval(dundamData)

print('1')
print(PRESETS)

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
