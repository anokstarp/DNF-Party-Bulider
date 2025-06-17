# app.py

import sqlite3
import os
from flask import Flask, redirect, url_for, current_app
from config import Config
from blueprints import blueprints as registered_blueprints

def get_db_connection():
    db_path = os.path.join(current_app.root_path, 'database', 'DB.sqlite')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # 템플릿 자동 갱신 설정
    app.config['TEMPLATES_AUTO_RELOAD'] = True

    for bp in registered_blueprints:
        app.register_blueprint(bp, url_prefix=f'/{bp.name}')

    @app.route('/')
    def index():
        return redirect(url_for('users.list_users'))

    return app

app = create_app()

if __name__ == '__main__':
    # 호스트와 디버그 모드 그대로 유지
    app.run(host='0.0.0.0', port=5000, debug=True)
