import sqlite3
import os
from flask import current_app

def get_db_connection():
    db_path = os.path.join(current_app.root_path, 'database', 'DB.sqlite')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn