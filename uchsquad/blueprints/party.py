import json
from flask import Blueprint, render_template, request, redirect, url_for, current_app
from utils import run_party_generation
from app import get_db_connection

party_bp = Blueprint('party', __name__, template_folder='../templates')

@party_bp.route('/', methods=['GET', 'POST'])
def list_and_generate():
    if request.method == 'POST':
        run_party_generation()
        return redirect(url_for('party.list_and_generate'))

    conn = get_db_connection()
    rows = conn.execute(
        'SELECT buffer, dealer1, dealer2, dealer3, result FROM party ORDER BY rowid DESC'
    ).fetchall()
    conn.close()

    parties = []
    for row in rows:
        # row는 sqlite3.Row이므로 dict(row)로 변환
        raw = dict(row)
        # 역할별 JSON 문자열을 파싱
        party = { role: json.loads(raw[role]) for role in raw }
        parties.append(party)

    # parties 리스트의 각 요소는
    # {
    #   'buffer':  {'chara_name':..., 'job':..., 'fame':..., 'score':...},
    #   'dealer1': {...}, ...
    # }
    return render_template('party.html', parties=parties)
