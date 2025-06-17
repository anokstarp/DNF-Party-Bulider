#!/usr/bin/env python3
import os
import sys
import sqlite3

def auto_place(adventure):
    # DB 파일 경로 (scripts 폴더 기준 상대 경로)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(os.path.dirname(script_dir), 'database', 'DB.sqlite')

    if not os.path.isfile(db_path):
        print(f"DB 파일을 찾을 수 없습니다: {db_path}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # 1) 해당 모험단 캐릭터 목록 조회
    cur.execute(
        "SELECT idx, fame FROM user_character WHERE adventure = ?",
        (adventure,)
    )
    rows = cur.fetchall()
    if not rows:
        print(f"모험단 '{adventure}' 의 캐릭터를 찾을 수 없습니다.", file=sys.stderr)
        conn.close()
        sys.exit(1)

    # fame 내림차순 정렬
    sorted_rows = sorted(rows, key=lambda r: r['fame'], reverse=True)

    # 2) 플래그 계산
    # 2a) nightmare: fame ≥ 52925 중 상위 4명
    top4 = [r['idx'] for r in sorted_rows if r['fame'] >= 52925][:4]

    updates = []
    for r in sorted_rows:
        idx = r['idx']
        fame = r['fame']
        nightmare = 1 if idx in top4 else 0
        temple    = 1 if fame >= 48988 else 0
        venus     = 1 if fame >= 41929 else 0
        azure     = 1 if fame >= 44929 and idx not in top4 else 0
        updates.append((nightmare, temple, azure, venus, idx))

    # 3) 일괄 업데이트
    cur.executemany(
        "UPDATE user_character "
        "SET nightmare = ?, temple = ?, azure = ?, venus = ? "
        "WHERE idx = ?",
        updates
    )
    conn.commit()
    conn.close()
    print("자동배치 완료:", adventure)

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("사용법: python auto_place.py <모험단 이름>", file=sys.stderr)
        sys.exit(1)
    auto_place(sys.argv[1])
