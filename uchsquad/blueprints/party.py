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

    if request.method == 'POST' and not request.form.get('complete_action'):
        # POST가 “재생성” 용도일 때만 파티 생성 스크립트 실행
        try:
            run_party_generation(role)
            conn = get_db_connection()
            buf_cnt = conn.execute(
                f"SELECT COUNT(*) FROM user_character "
                f"WHERE use_yn=1 AND isbuffer=1 AND {role}=1"
            ).fetchone()[0]
            del_cnt = conn.execute(
                f"SELECT COUNT(*) FROM user_character "
                f"WHERE use_yn=1 AND isbuffer=0 AND {role}=1"
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

    # GET 요청 또는 완료/복원 액션 이후
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT id, buffer, dealer1, dealer2, dealer3, result, "
        "       COALESCE(is_completed, 0) AS is_completed "
        "FROM party WHERE type = ? ORDER BY id ASC",
        (role,)
    ).fetchall()

    parties = []
    for r in rows:
        # SQLite TEXT 컬럼에서 '0'/'1'로 왔다면 int() 로 변환한 뒤 bool로
        completed_flag = False
        try:
            completed_flag = bool(int(r['is_completed']))
        except Exception:
            # 만약 이미 0/1 정수형으로 왔으면 그냥 bool으로
            completed_flag = bool(r['is_completed'])

        # ① buffer JSON 로드 & isbuffer bool 변환
        buf = json.loads(r['buffer'])
        buf['isbuffer'] = bool(int(buf.get('isbuffer', 0)))

        # ② dealers JSON 로드 & isbuffer bool 변환
        dealers = []
        for key in ('dealer1', 'dealer2', 'dealer3'):
            raw = r[key]
            if raw:
                d = json.loads(raw)
                d['isbuffer'] = bool(int(d.get('isbuffer', 0)))
                dealers.append(d)
            else:
                dealers.append(None)

        parties.append({
            'id': r['id'],
            'buffer': buf,
            'dealers': dealers,
            'result': r['result'],
            'is_completed': completed_flag,
        })

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

@party_bp.route('/complete', methods=['POST'])
def complete_party():
    """파티를 완료 상태로 표시합니다."""
    party_id = request.form.get('party_id')
    role     = request.form.get('role', 'temple')

    if not party_id:
        flash('유효하지 않은 파티입니다.', 'error')
    else:
        conn = get_db_connection()
        conn.execute(
            'UPDATE party SET is_completed = 1 WHERE id = ?',
            (party_id,)
        )
        conn.commit()
        conn.close()
        flash(f'파티 {party_id}를 클리어 처리했습니다.', 'success')

    return redirect(url_for('party.list_and_generate', role=role))

@party_bp.route('/uncomplete', methods=['POST'])
def uncomplete_party():
    """완료된 파티를 미완료 상태로 되돌립니다."""
    party_id = request.form.get('party_id')
    role     = request.form.get('role', 'temple')

    if not party_id:
        flash('유효하지 않은 파티입니다.', 'error')
    else:
        conn = get_db_connection()
        conn.execute(
            'UPDATE party SET is_completed = 0 WHERE id = ?',
            (party_id,)
        )
        conn.commit()
        conn.close()
        flash(f'파티 {party_id}를 미완료 상태로 되돌렸습니다.', 'success')

    return redirect(url_for('party.list_and_generate', role=role))

def format_korean(num):
    parts = []
    eok = num // 100_000_000
    if eok:
        parts.append(f"{eok}억")
        num %= 100_000_000
    man = num // 10_000
    if man:
        parts.append(f"{man}만")
    return " ".join(parts) or "0"
    
party_bp.add_app_template_filter(format_korean, 'korean')