# 몽키 슬랙봇

식단 알림, 간단한 잡담 응답, 사다리타기, 세탁 현황 조회, 공지/예약 메시지, 선택형 코칭룸 예약 기능을 담은 Slack 봇 예시 프로젝트입니다.

이 저장소는 공개 또는 보관을 위해 정리한 버전입니다. 실제 운영 토큰, 서버 주소, SSH 키, 개인 대화 기록, 실제 외부 서비스 주소는 포함하지 않습니다.

## 주요 기능

- 점심/저녁 메뉴 조회
- 점심/저녁 자동 알림
- 외부 게시글 기반 메뉴 동기화
- 외부 API 기반 세탁 현황 조회
- GIF 사다리타기와 지연 결과 공개
- DM 기반 공지 및 예약 메시지
- OpenAI 기반 짧은 잡담 응답
- 사용자별 잡담 말투 예시
- 외부 API 기반 코칭룸 예약 연동

## 포함된 파일

- `monkey_bot.py`: 봇 메인 코드
- `data/menu.json`: 로컬 실행용 샘플 메뉴
- `data/user_personas.example.json`: 사용자별 말투 설정 예시
- `.env.example`: 환경변수 예시
- `.gitignore`: 민감 파일과 실행 중 생성되는 상태 파일 제외
- `monkey-bot.service`: 일반화된 systemd 서비스 예시
- `scripts/setup_ubuntu.sh`: 일반 Ubuntu 서버 설치 예시

## 제외한 것

아래 항목은 공개 저장소에 넣지 않습니다.

- `.env`
- Slack/OpenAI 토큰
- SSH 키와 private key
- 실제 서버 IP, 접속 계정, 배포 명령
- 실제 Slack 채널 ID, 사용자 ID
- 실제 외부 서비스 URL
- 대화 기억, 사용자 기억, 예약 메시지, 동기화 상태 파일

## 로컬 실행

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python monkey_bot.py --check
python monkey_bot.py --preview "오늘 점심"
```

Linux/macOS:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python monkey_bot.py --check
python monkey_bot.py --preview "오늘 점심"
```
