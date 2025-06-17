# utils.py

import subprocess
from app import get_db_connection

def run_party_generation():
    """
    이미 구현된 외부 Python 스크립트나 함수로
    party 테이블을 갱신하는 로직을 호출합니다.
    예를 들어, 별도 스크립트(party_gen.py)를 실행하거나
    내부 함수(party_generator.generate())를 호출하도록 구성합니다.
    """
    # 외부 스크립트 실행
    subprocess.run(['python', 'party_gen.py'], check=True)

    # 만약 외부 스크립트가 직접 DB를 수정하지 않는다면,
    # 명시적으로 커밋이 필요할 수 있습니다:
    conn = get_db_connection()
    conn.commit()
    conn.close()
