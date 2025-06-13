import requests
import subprocess
import ast

SCRAPE_SCRIPT = 'scrap_char.py'
PYTHON_EXEC = 'python'

REQUEST_TEMPLATE = "https://dundam.xyz/dat/viewData.jsp?image={key}&server={server}&"


def fetch_request_urls(tuples):
    
    tuples: [(server, char_id), ...]
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})

    for server, key in tuples:
        request_url = REQUEST_TEMPLATE.format(server=server, key=key)
        try:
            resp = session.get(request_url, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            # 두 키 모두 존재하면 성공, 그 외는 실패
            if 'adventure' in data and 'name' in data:
                print(f"{data['adventure']}({data['name']}, {data['job']}, {data['fame']})")
            else:
                adv = data.get('adventure', server)
                print(f"{adv} : {key} 갱신 실패")
        except requests.RequestException as e:
            print(f"{server} : {key} 갱신 실패 (에러: {e})")


def load_tuples_from_subprocess():
    """
    SCRAPE_SCRIPT를 서브프로세스로 실행하여
    표준 출력된 튜플 문자열을 실제 튜플로 변환해 반환한다.
    """
    result = subprocess.run(
        [PYTHON_EXEC, SCRAPE_SCRIPT],
        capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        print(f"스크랩 스크립트 오류 (exit code {result.returncode}):")
        print(result.stderr.strip())
        return []
    tuples = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            tup = ast.literal_eval(line)
            if isinstance(tup, tuple) and len(tup) == 2:
                tuples.append(tup)
        except Exception:
            continue
    return tuples


if __name__ == '__main__':
    server_char_tuples = load_tuples_from_subprocess()
    if not server_char_tuples:
        print("유효한 서버/키 튜플이 없습니다. 스크랩 스크립트 확인 필요.")
    else:
        fetch_request_urls(server_char_tuples)
