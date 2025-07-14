# blueprints/user_characters_api.py

from flask import Blueprint, Response
from db import get_db_connection
import json

user_characters_bp = Blueprint('user_characters_api', __name__, url_prefix='/api')

@user_characters_bp.route('/user_characters', methods=['GET'])
def get_user_characters():
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT server, chara_name, adventure AS adv FROM user_character"
    ).fetchall()
    conn.close()

    # → 명시적으로 순서대로 dict 생성
    data = [
        {
            "server":    row["server"],
            "chara_name": row["chara_name"],
            "adv":       row["adv"]
        }
        for row in rows
    ]
    # ensure_ascii=False 로 한글이 그대로 나오도록 하고,
    # Content-Type 에 charset=utf-8 을 명시해 줍니다.
    body = json.dumps(data, ensure_ascii=False)
    return Response(body, content_type='application/json; charset=utf-8')