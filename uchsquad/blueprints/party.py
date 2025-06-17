import os
import json
from flask import Blueprint, render_template, request, redirect, url_for
from scripts.party_generator import run_party_generation
from app import get_db_connection

# __file__ 기준으로 project_root/templates 폴더를 가리키도록 절대 경로 설정
TEMPLATES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'templates'))

party_bp = Blueprint(
    'party',
    __name__,
    template_folder=TEMPLATES_DIR
)

@party_bp.route('/', methods=['GET', 'POST'])
def list_and_generate():
    # 1) 선택된 파티 타입 (기본 'temple')
    selected = request.values.get('type', 'temple')

    # 2) POST → 선택된 타입 파티 재생성
    if request.method == 'POST':
        run_party_generation(selected)
        return redirect(url_for('party.list_and_generate', type=selected))

    # 3) GET → 단일 'party' 테이블에서 해당 타입만 오름차순 조회
    conn = get_db_connection()
    rows = conn.execute(
        'SELECT id, type, buffer, dealer1, dealer2, dealer3 '
        'FROM party '
        'WHERE type = ? '
        'ORDER BY id ASC',
        (selected,)
    ).fetchall()
    conn.close()

    parties = []
    for row in rows:
        raw = dict(row)
        parties.append({
            'id':     raw['id'],
            'type':   raw['type'],
            'buffer': json.loads(raw['buffer']) if raw['buffer'] else None,
            'dealers': [
                json.loads(raw['dealer1']) if raw['dealer1'] else None,
                json.loads(raw['dealer2']) if raw['dealer2'] else None,
                json.loads(raw['dealer3']) if raw['dealer3'] else None,
            ]
        })

    return render_template('party.html',
                           selected=selected,
                           parties=parties)
