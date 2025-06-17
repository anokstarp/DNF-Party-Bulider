# config.py

import os

# 이 파일(config.py)이 위치한 디렉터리(프로젝트 루트)의 절대 경로
basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key')
    # 절대 경로로 SQLite 파일을 지정
    SQLALCHEMY_DATABASE_URI = (
        'sqlite:///' +
        os.path.join(basedir, 'database', 'DB.sqlite')
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
