from flask import Blueprint, render_template, request, redirect, url_for, current_app
import sqlite3
import os

users_bp = Blueprint('users', __name__, template_folder='../templates')

# blueprints/users.py

from flask import Blueprint, render_template, request, redirect, url_for, current_app
import sqlite3
import os

users_bp = Blueprint('users', __name__, template_folder='../templates')

def get_db_connection():
    db_path = os.path.join(current_app.root_path, 'database', 'DB.sqlite')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

@users_bp.route('/', methods=['GET'])
def list_users():
    conn = get_db_connection()
    rows = conn.execute(
        'SELECT idx, "user" AS name, adventure FROM user_adventure ORDER BY idx'
    ).fetchall()
    conn.close()
    users = [dict(r) for r in rows]
    return render_template('users.html', users=users, alert=None)

@users_bp.route('/add', methods=['POST'])
def add_user():
    name = request.form['name']
    adv  = request.form['adventure']
    conn = get_db_connection()

    # 1) 중복 체크: 같은 adventure가 이미 존재하는지
    exists = conn.execute(
        'SELECT 1 FROM user_adventure WHERE adventure = ?',
        (adv,)
    ).fetchone()

    if exists:
        # 중복일 경우, 경고 메시지를 list_users에 전달
        rows = conn.execute(
            'SELECT idx, "user" AS name, adventure FROM user_adventure ORDER BY idx'
        ).fetchall()
        conn.close()
        users = [dict(r) for r in rows]
        return render_template(
            'users.html',
            users=users,
            alert='이미 있는 모험단입니다.'
        )

    # 2) 중복 아니라면 삽입
    conn.execute(
        'INSERT INTO user_adventure ("user", adventure) VALUES (?, ?)',
        (name, adv)
    )
    conn.commit()
    conn.close()

    return redirect(url_for('users.list_users'))


@users_bp.route('/delete', methods=['POST'])
def delete_user():
    idx = request.form.get('idx', type=int)
    conn = get_db_connection()
    conn.execute(
        'DELETE FROM user_adventure WHERE idx = ?',
        (idx,)
    )
    conn.commit()
    conn.close()
    return redirect(url_for('users.list_users'))