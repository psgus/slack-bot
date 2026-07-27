# 몽키 Slack Bot 보관본

몽키 Slack Bot의 공개 가능한 코드와 실행 예시를 보관한 날짜별 사본입니다.

## 포함된 기능

- 점심·저녁 메뉴 조회와 알림
- 카카오 게시글 기반 메뉴 동기화
- 세탁 현황 조회
- 사다리타기
- 공지·예약 메시지
- 코칭실 예약 조회와 예약
- 선택형 OpenAI 대화

## 실행 방법

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python monkey_bot.py --check
python monkey_bot.py
```

Windows에서는 다음 명령을 사용합니다.

```powershell
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python monkey_bot.py --check
```

실행 전에 `.env`에 Slack 토큰과 필요한 설정을 입력해야 합니다.

## 파일 안내

- `monkey_bot.py`: 봇 코드
- `.env.example`: 환경변수 예시
- `data/menu.json`: 샘플 메뉴
- `monkey-bot.service`: systemd 실행 예시
- `Dockerfile`: Docker 실행 예시

## 공개 범위

- 실제 서버 정보, 토큰, SSH 키는 포함하지 않습니다.
- 개인 대화 기록과 운영 상태 파일은 공개하지 않습니다.
- 코칭실 예약은 사용자의 Slack 요청으로 실행되며 자동 예약 스케줄러는 포함되어 있지 않습니다.

이 폴더는 현재 운영본이 아닌 공개용 보관 사본입니다.
