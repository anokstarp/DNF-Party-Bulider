from flask import Blueprint, render_template, request, redirect, url_for, current_app
from flask import jsonify
import subprocess
import sys
import os
from datetime import datetime

from db import get_db_connection

characters_bp = Blueprint('characters', __name__, template_folder='../templates')

# 전역 플래그
is_updating  = False     # update_score 용
is_placing = False       # auto_place 용

@characters_bp.route('/', methods=['GET'])
def show_characters():
    alert = request.args.get('alert')

    conn = get_db_connection()
    users = [dict(r) for r in conn.execute(
        'SELECT idx, "user" AS name, adventure FROM user_adventure ORDER BY idx'
    ).fetchall()]

    user_idx      = request.args.get('user_idx', type=int)
    selected_user = None
    characters    = []
    last_exec     = None               # ← 여기에 초기화
    summary = {
        'temple': (0, 0, 0),
        'azure' : (0, 0, 0),
        'venus' : (0, 0, 0),
        'tmp'   : (0, 0, 0),
    }

    if user_idx:
        # ── 1) 이번 주 마지막 목요일 06:00 시각 계산 ──
        from datetime import datetime, timedelta
        now = datetime.now()
        # Python: weekday() 월=0…일=6, 목요일=3
        days_since_thu = (now.weekday() - 3) % 7
        last_thu = now - timedelta(days=days_since_thu)
        reset_dt = last_thu.replace(hour=6, minute=0, second=0, microsecond=0)
        reset_str = reset_dt.strftime('%Y-%m-%d %H:%M:%S')        
        
        row = conn.execute(
            'SELECT idx, "user" AS name, adventure FROM user_adventure WHERE idx = ?',
            (user_idx,)
        ).fetchone()

        if row is None:
            # 원하는 처리: 404, 리다이렉트, 첫 사용자 자동 선택 등
            return redirect(url_for('characters.show_characters',
                                    alert='존재하지 않는 유저입니다.'))

        selected_user = dict(row)

        # 1) 일단 sort_order가 NULL인 행은 idx 값으로 자동 채워 넣기
        #    (화면에만 보이도록 하고, DB에도 업데이트)
        rows = conn.execute(
            'SELECT idx, display_order FROM user_character WHERE adventure = ?',
            (selected_user['adventure'],)
        ).fetchall()
        for r in rows:
            if r['display_order'] is None:
                conn.execute(
                    'UPDATE user_character SET display_order = ? WHERE idx = ?',
                    (r['idx'], r['idx'])
                )
        conn.commit()

        # 2) 순서대로 캐릭터 목록 조회
        characters = [dict(r) for r in conn.execute(
            '''
            SELECT
              idx, server, key, chara_name, job, fame,
              score,
              NULL           AS last_score,   -- placeholder
              isbuffer, nightmare, temple, azure, venus, tmp, use_yn,
              display_order
            FROM user_character
            WHERE adventure = ?
            ORDER BY
              CASE WHEN display_order IS NULL THEN 1 ELSE 0 END,
              display_order ASC,
              idx ASC
            ''',
            (selected_user['adventure'],)
        ).fetchall()]


        # ── 3) character_history 에서 reset 이전의 가장 최신 이력 점수로 last_score 덮어쓰기 ──
        for c in characters:
            row = conn.execute(
                '''
                SELECT score
                  FROM character_history
                 WHERE chara_name = ?
                   AND server     = ?
                   AND updated_at < ?
                 ORDER BY updated_at DESC
                 LIMIT 1
                ''',
                (c['chara_name'], c['server'], reset_str)
            ).fetchone()
            c['last_score'] = row['score'] if row else c['score']

        
        # 3) 마지막 갱신 시각 조회
        row2 = conn.execute(
            'SELECT date FROM last_execute '
            'WHERE command = ? AND user = ?',
            ('update_score.py', selected_user['adventure'])
        ).fetchone()
        if row2:
            last_exec = row2['date']
    
    
        # 4) use_yn=1 캐릭터만 골라서 D/B 집계
        counts = {cat: {'D': 0, 'B': 0} for cat in ('temple','azure','venus','tmp')}
        for r in conn.execute(
            'SELECT isbuffer, temple, azure, venus, tmp '
            '  FROM user_character '
            ' WHERE adventure = ? AND use_yn = 1',
            (selected_user['adventure'],)
        ).fetchall():
            buf = r['isbuffer']
            for cat in counts:
                if r[cat]:
                    counts[cat][ buf and 'B' or 'D' ] += 1

        # summary = { 'temple':(total,D,B), … }
        summary = {
            cat: (counts[cat]['D']+counts[cat]['B'],
                  counts[cat]['D'],
                  counts[cat]['B'])
            for cat in counts
        }
    
    conn.close()
    
    return render_template(
        'characters.html',
        users=users,
        selected_user=selected_user,
        characters=characters,
        last_exec=last_exec,          # now defined
        summary=summary,
        alert=alert
    )



@characters_bp.route('/update_score', methods=['POST'])
def update_score_for_user():
    global is_updating

    user_idx  = request.form.get('user_idx', type=int)
    adventure = request.form.get('adventure')
    if not user_idx or not adventure:
        return redirect(url_for('characters.show_characters',
                                alert='유저/모험단 정보를 확인해 주세요.'))

    if is_updating:
        return redirect(url_for('characters.show_characters',
                                user_idx=user_idx,
                                alert='이미 점수 갱신 중입니다.'))

    is_updating = True
    try:
        # 1) 스크립트 실행 (venv 보장, 타임아웃 및 출력 캡처)
        script_path = os.path.join(current_app.root_path, 'scripts', 'update_score.py')
        cp = subprocess.run(
            [sys.executable, script_path, adventure],
            check=True,
            capture_output=True,
            text=True,
            timeout=90,
        )
        current_app.logger.info("update_score.py stdout: %s", cp.stdout[:2000])

        # 2) 실행 성공 시 last_execute 테이블에 기록
        conn = get_db_connection()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        conn.execute(
            '''
            INSERT INTO last_execute (command, user, date)
            VALUES (?, ?, ?)
            ON CONFLICT(command, user) DO UPDATE SET date=excluded.date
            ''',
            ('update_score.py', adventure, now)
        )
        conn.commit()
        conn.close()

    except subprocess.TimeoutExpired as e:
        current_app.logger.error("update_score.py timeout: %ss", e.timeout)
        return redirect(url_for('characters.show_characters',
                                user_idx=user_idx,
                                alert='점수 업데이트가 시간 초과되었습니다.'))
    except subprocess.CalledProcessError as e:
        current_app.logger.error(
            "update_score.py failed: rc=%s stderr=%s", e.returncode, e.stderr[:2000]
        )
        return redirect(url_for('characters.show_characters',
                                user_idx=user_idx,
                                alert='점수 업데이트 중 오류가 발생했습니다.'))
    finally:
        is_updating = False

    return redirect(url_for('characters.show_characters',
                            user_idx=user_idx,
                            alert='점수 업데이트 완료!'))
                            
@characters_bp.route('/update_flags', methods=['POST'])
def update_flags():
    # 1) 폼에서 모험단/user_idx 가져오기
    user_idx  = request.form.get('user_idx', type=int)
    adventure = request.form.get('adventure')
    if not user_idx or not adventure:
        return redirect(
            url_for('characters.show_characters',
                    alert='유저 정보를 확인해 주세요.')
        )

    conn = get_db_connection()
    # 2) 이 모험단에 속한 모든 캐릭터의 idx 조회
    rows = conn.execute(
        'SELECT idx FROM user_character WHERE adventure = ?',
        (adventure,)
    ).fetchall()

    # 3) 각 idx마다 체크박스 값을 읽어서 업데이트
    for r in rows:
        idx = r['idx']
        nightmare = 1 if request.form.get(f'nightmare_{idx}') else 0
        temple    = 1 if request.form.get(f'temple_{idx}')     else 0
        azure     = 1 if request.form.get(f'azure_{idx}')      else 0
        venus     = 1 if request.form.get(f'venus_{idx}')      else 0
        tmp       = 1 if request.form.get(f'tmp_{idx}')        else 0
        use_yn    = 1 if request.form.get(f'use_yn_{idx}')     else 0

        conn.execute(
            '''
            UPDATE user_character
               SET nightmare = ?,
                   temple    = ?,
                   azure     = ?,
                   venus     = ?,
                   tmp       = ?,
                   use_yn    = ?
             WHERE idx = ?
            ''',
            (nightmare, temple, azure, venus, tmp, use_yn, idx)
        )

    conn.commit()
    conn.close()

    # 4) 완료 후 원래 페이지로 리다이렉트
    return redirect(
        url_for('characters.show_characters',
                user_idx=user_idx,
                alert='역할이 저장되었습니다.')
    )
    
    
@characters_bp.route('/auto_place', methods=['POST'])
def auto_place():
    global is_placing
    user_idx  = request.form.get('user_idx', type=int)
    adventure = request.form.get('adventure')
    if not user_idx or not adventure:
        return redirect(url_for('characters.show_characters',
                                alert='유저를 선택해 주세요.'))

    if is_placing:
        return redirect(url_for('characters.show_characters',
                                user_idx=user_idx,
                                alert='자동배치가 이미 실행 중입니다.'))

    is_placing = True
    try:
        script = os.path.join(current_app.root_path, 'scripts', 'auto_place.py')
        subprocess.run(['python', script, adventure], check=True, encoding='utf-8')
    except subprocess.CalledProcessError:
        return redirect(url_for('characters.show_characters',
                                user_idx=user_idx,
                                alert='자동배치 중 오류가 발생했습니다.'))
    finally:
        is_placing = False

    return redirect(url_for('characters.show_characters',
                            user_idx=user_idx,
                            alert='자동배치 완료!'))
                            


@characters_bp.route('/swap_order', methods=['POST'])
def swap_order():
    """
    JSON body: { a: <idx1>, b: <idx2> }
    두 캐릭터의 display_order 값을 서로 교환합니다.
    """
    data = request.get_json() or {}
    a_idx = data.get('a')
    b_idx = data.get('b')

    # 클라이언트에서 잘못된 값이 넘어오면 조기에 에러 처리
    try:
        a_idx = int(a_idx)
        b_idx = int(b_idx)
    except (TypeError, ValueError):
        return jsonify({'status': 'error', 'msg': '잘못된 요청입니다.'}), 400

    conn = get_db_connection()
    # 1) 현재 순서값 읽기
    row = conn.execute(
        'SELECT display_order FROM user_character WHERE idx=?',
        (a_idx,)
    ).fetchone()
    row2 = conn.execute(
        'SELECT display_order FROM user_character WHERE idx=?',
        (b_idx,)
    ).fetchone()
    if not row or not row2:
        conn.close()
        return jsonify({'status': 'error', 'msg': '존재하지 않는 캐릭터입니다.'}), 404

    a_order, b_order = row['display_order'], row2['display_order']

    # 2) 두 행을 하나의 쿼리로 동시에 교환하여 중간 상태에서 값이 같아지는 문제를 방지
    conn.execute(
        '''
        UPDATE user_character
           SET display_order = CASE idx
                                  WHEN ? THEN ?
                                  WHEN ? THEN ?
                                END
         WHERE idx IN (?, ?)
        ''',
        (a_idx, b_order, b_idx, a_order, a_idx, b_idx)
    )
    conn.commit()
    conn.close()

    return jsonify({'status': 'ok'})



@characters_bp.route('/history', methods=['GET'])
def character_history():
    try:
        name   = request.args.get('chara_name')
        server = request.args.get('server')
        if not name or not server:
            return jsonify({'error': 'missing parameters'}), 400

        conn = get_db_connection()
        rows = conn.execute(
            """
            SELECT h.fame,
                   h.score,
                   h.updated_at,
                   c.job
              FROM character_history AS h
              JOIN user_character AS c
                ON h.chara_name = c.chara_name
               AND h.server     = c.server
             WHERE h.chara_name = ?
               AND h.server     = ?
             ORDER BY h.updated_at DESC
            """,
            (name, server)
        ).fetchall()
        conn.close()

        result = []
        for r in rows:
            result.append({
                'fame':       r['fame'],
                'score':      r['score'],
                'updated_at': r['updated_at'],
                'job':        r['job'],
            })
        return jsonify(result)
    except Exception as e:
        import traceback
        print(traceback.format_exc())  # 콘솔에 에러 전체 스택 출력
        return jsonify({'error': '서버 내부 오류', 'message': str(e)}), 500
