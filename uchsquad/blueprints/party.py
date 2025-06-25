import os
import sys
import subprocess
import json
from flask import Blueprint, render_template, request, redirect, url_for, flash
from app import get_db_connection
from scripts.party_maker_print import compute_party_score

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
        raw_buf = r['buffer']
        if raw_buf:
            buf = json.loads(raw_buf)
            buf['isbuffer'] = bool(int(buf.get('isbuffer', 0)))
        else:
            buf = None


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
            'is_completed': bool(int(r['is_completed'])),
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


@party_bp.route('/swap', methods=['POST'])
def swap_members():
    data = request.get_json()
    party_id = data['party_id']
    conn = get_db_connection()
    
    out = data.get('out', {})
    inn = data.get('in', {})
    
    has_out = bool(out.get('adventure') and out['adventure'] != '—')
    has_in  = bool(inn .get('adventure') and inn ['adventure'] != '—')
    
    # OUT만 있을 때
    if has_out and not has_in:
        if out['role'] == 'buffer':
            col = 'buffer'
        else:
            col = f"dealer{int(out['slot']) + 1}"

        conn.execute(f"UPDATE party SET {col} = NULL WHERE id = ?", (party_id,))

        # 2. chara_name에서 (직업) 분리
        pure_name = out['chara_name'].split(' (')[0].strip()
        orig = conn.execute(
            "SELECT adventure, chara_name, job, fame, score, isbuffer FROM user_character WHERE adventure = ? AND chara_name = ?",
            (out['adventure'], pure_name)
        ).fetchone()
        if orig:
            orig_dict = dict(orig)
            # 3. abandonment에 완성된 데이터 저장!
            conn.execute(
                "INSERT INTO abandonment (type, character) VALUES (?, ?)",
                (data['role'], json.dumps(orig_dict, ensure_ascii=False))
            )
        else:
            print("OUT시 원본 캐릭터를 못찾음!", out['adventure'], pure_name)


    elif has_in and not has_out:
        # 1) 슬롯 기반으로 col 결정 (0→buffer, 그 외→dealer)
        slot = int(out.get('slot') or inn.get('slot'))
        if slot == 0:
            col = 'buffer'
        else:
            col = f"dealer{slot+1}"

        # 2) 동일 모험단 중복 체크
        row = conn.execute(
            "SELECT buffer, dealer1, dealer2, dealer3 FROM party WHERE id = ?",
            (party_id,)
        ).fetchone()
        advs = set()
        for raw in (row['buffer'], row['dealer1'], row['dealer2'], row['dealer3']):
            if raw and raw not in ('null', '', None):
                try:
                    mem = json.loads(raw)
                    advs.add(mem['adventure'])
                except Exception:
                    pass
        if inn['adventure'] in advs:
            conn.close()
            return ('동일 모험단 캐릭터가 이미 파티에 있습니다!', 409)

        # 3) abandonment에서 완성된 JSON 데이터 바로 SELECT
        pure_name = inn['chara_name'].split(' (')[0].strip()
        row = conn.execute(
            """
            SELECT character
              FROM abandonment
             WHERE type = ?
               AND json_extract(character, '$.adventure') = ?
               AND json_extract(character, '$.chara_name') = ?
            """,
            (data['role'], inn['adventure'], pure_name)
        ).fetchone()
        
        if not row:
            conn.close()
            return ('abandonment에서 해당 캐릭터를 찾을 수 없습니다!', 404)
        target = json.loads(row['character'])

        # 4) abandonment에서 삭제 후 party에 저장
        conn.execute(
            "DELETE FROM abandonment WHERE type = ? AND character = ?",
            (data['role'], json.dumps(target, ensure_ascii=False))
        )
        conn.execute(
            f"UPDATE party SET {col} = ? WHERE id = ?",
            (json.dumps(target, ensure_ascii=False), party_id)
        )


    elif has_out and has_in:
        # ── 1) OUT 처리 ──
        # 1-1) 파티에서 OUT 슬롯 비우기
        slot = int(out.get('slot') or inn.get('slot'))
        col_out = 'buffer' if slot==0 else f"dealer{slot+1}"
        conn.execute(f"UPDATE party SET {col_out}=NULL WHERE id=?", (party_id,))

        # 1-2) DB에서 원본 캐릭터 조회 → abandonment
        pure_out = out['chara_name'].split(' (')[0].strip()
        orig = conn.execute(
            "SELECT adventure,chara_name,job,fame,score,isbuffer "
            "FROM user_character WHERE adventure=? AND chara_name=?",
            (out['adventure'], pure_out)
        ).fetchone()
        if orig:
            conn.execute(
                "INSERT INTO abandonment(type,character) VALUES(?,?)",
                (data['role'], json.dumps(dict(orig), ensure_ascii=False))
            )
        else:
            print("SWAP-OUT: 원본 캐릭터 못찾음!", out['adventure'], pure_out)

        # ── 2) 중복 체크 ──
        row = conn.execute(
            "SELECT buffer,dealer1,dealer2,dealer3 FROM party WHERE id=?",
            (party_id,)
        ).fetchone()
        advs = {
            json.loads(x)['adventure']
            for x in (row['buffer'],row['dealer1'],row['dealer2'],row['dealer3'])
            if x and x not in ('null','',None)
        }
        advs.discard(out['adventure'])
        if inn['adventure'] in advs:
            conn.close()
            return ('동일 모험단 캐릭터가 이미 파티에 있습니다!', 409)

        # ── 3) IN 처리 ──
        # 3-1) 슬롯 결정 (out/inn 중 있는 쪽에서)
        slot = int(out.get('slot') or inn.get('slot'))
        col_in = 'buffer' if slot==0 else f"dealer{slot+1}"

        # 3-2) 이미 abandonment에 있는 완성형 JSON 꺼내기
        pure_in = inn['chara_name'].split(' (')[0].strip()
        r = conn.execute(
            """
            SELECT character
              FROM abandonment
             WHERE type=?
               AND json_extract(character,'$.adventure')=?
               AND json_extract(character,'$.chara_name')=?
            """,
            (data['role'], inn['adventure'], pure_in)
        ).fetchone()
        if not r:
            conn.close()
            return ('abandonment에서 IN할 캐릭터를 찾을 수 없습니다!',404)
        target = json.loads(r['character'])

        # 3-3) abandonment에서 삭제하고 파티에 업데이트
        conn.execute(
            "DELETE FROM abandonment WHERE type=? AND character=?",
            (data['role'], json.dumps(target, ensure_ascii=False))
        )
        col_in = col_out
        conn.execute(
            f"UPDATE party SET {col_in}=? WHERE id=?",
            (json.dumps(target, ensure_ascii=False), party_id)
        )




    # 3) 합산 점수 재계산
    # 기존 스크립트를 참고해서 members 리스트를 불러온 뒤
    rows = conn.execute(
        "SELECT buffer, dealer1, dealer2, dealer3 FROM party WHERE id = ?",
        (party_id,)
    ).fetchone()
    
    if not rows:
        print(f"party id {party_id}가 존재하지 않음!")
        conn.close()
        return ('', 404)  # 또는 에러 처리
    
    members = []
    for raw in (rows['buffer'], rows['dealer1'], rows['dealer2'], rows['dealer3']):
        # raw가 None(빈 슬롯)이면 무시
        if raw is not None and raw != 'null' and raw != '':
            try:
                m = json.loads(raw)
                m['is_buffer'] = bool(m.get('isbuffer', 0))
                members.append(m)
            except Exception as e:
                # 혹시라도 이상한 데이터 들어오면 무시하고 계속 진행
                print("멤버 로딩 중 오류:", e)
                continue
    # 여기서는 scripts/party_maker_print.py 의 compute_party_score 함수를 import 해서 사용
    new_score = compute_party_score(members)
    conn.execute(
        "UPDATE party SET result = ? WHERE id = ?",
        (new_score, party_id)
    )

    conn.commit()
    conn.close()
    return ('', 204)
