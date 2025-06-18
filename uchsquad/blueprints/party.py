import os
import sys
import subprocess
import json
from flask import Blueprint, render_template, request, redirect, url_for, flash
from app import get_db_connection

party_bp = Blueprint('party', __name__, url_prefix='/party')

def run_party_generation(role):
    base_dir    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    script_path = os.path.join(base_dir, 'scripts', 'party_maker_print.py')
    return subprocess.run(
        [sys.executable, script_path, role],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

@party_bp.route('/', methods=['GET', 'POST'])
def list_and_generate():
    role = request.values.get('role', 'temple')

    if request.method == 'POST':
        try:
            # 1) 파티 생성 스크립트 실행
            res = run_party_generation(role)

            # 2) 생성 후 DB에서 버퍼·딜러·파티 개수 조회
            conn = get_db_connection()
            buf_cnt = conn.execute(
                f"SELECT COUNT(*) FROM user_character "
                f"WHERE use_yn=1 AND isbuffer=1 AND {role}=1"
            ).fetchone()[0]
            del_cnt = conn.execute(
                "SELECT COUNT(*) FROM user_character "
                "WHERE use_yn=1 AND isbuffer=0"
            ).fetchone()[0]
            party_cnt = conn.execute(
                "SELECT COUNT(*) FROM party WHERE type = ?",
                (role,)
            ).fetchone()[0]
            conn.close()

            flash(
                f"버퍼 {buf_cnt}명, 딜러 {del_cnt}명 (총 {buf_cnt + del_cnt}명) → "
                f"{party_cnt}개 파티 생성 완료",
                "success"
            )
        except subprocess.CalledProcessError as e:
            err = e.stderr.strip() if e.stderr else str(e)
            flash(f"파티 재생성 중 오류 발생:\n{err}", "error")

        return redirect(url_for('party.list_and_generate', role=role))

    # GET 요청: party / abandonment 로드
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT buffer, dealer1, dealer2, dealer3, result "
        "FROM party WHERE type = ? ORDER BY id ASC",
        (role,)
    ).fetchall()
    parties = [{
        'buffer': json.loads(r['buffer']),
        'dealers': [
            json.loads(r['dealer1']) if r['dealer1'] else None,
            json.loads(r['dealer2']) if r['dealer2'] else None,
            json.loads(r['dealer3']) if r['dealer3'] else None,
        ],
        'result': r['result']
    } for r in rows]

    ab_rows = conn.execute(
        "SELECT character FROM abandonment WHERE type = ? ORDER BY id ASC",
        (role,)
    ).fetchall()
    abandoned = [json.loads(r['character']) for r in ab_rows]
    conn.close()

    return render_template(
        'party.html',
        selected=role,
        parties=parties,
        abandoned=abandoned
    )
