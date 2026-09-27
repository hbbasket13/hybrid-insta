# clinic-insta — Hybrid Physiotherapy 인스타그램 자동화

Google Sheets 대신 이 저장소 하나로 돌아가는 구조입니다. 카피 생성(Claude API) → 카드뉴스 렌더링(Playwright) → 검토 승인 → Instagram Graph API 발행까지 GitHub Actions가 처리하고, 사람은 주 1회 10분 검토만 하면 됩니다.

```
topics.csv ──generate.py──▶ drafts/*.json ──render.py──▶ assets/<id>/slide-NN.png, story.png
                                  │
                        (검토 후 approve.py 또는 파일 이동)
                                  ▼
                           approved/*.json ──publish.py──▶ Instagram (캐러셀 + 스토리) ──▶ posted/
reel_script 포맷은 reels/*.md 로 나옵니다 (촬영용 대본 + 캡션, 발행은 수동)
```

서비스: physio · chiro · pilates · remedial · clinic(공통/FAQ). 뷰티 제외, before/after·후기·보장 문구는 프롬프트와 검증기에서 모두 차단됩니다 (`config/compliance.md`).

---

## 1. 최초 설정 (한 번만)

### 1-1. 저장소
1. GitHub에 새 저장소 생성 → 이 폴더 전체 업로드.
2. **저장소는 Public** 으로 두세요. Instagram이 이미지를 가져가려면 `assets/` PNG가 공개 URL이어야 하고, 기본 설정은 `https://raw.githubusercontent.com/<owner>/<repo>/main/assets/...` 입니다. (비밀키는 전부 GitHub Secrets에 있으므로 저장소 자체에는 민감정보가 없습니다.)
   - Private으로 꼭 두고 싶으면: 이미지 전용 Public 저장소를 하나 더 만들어 `assets/`를 그쪽에 커밋하고 `PUBLIC_BASE_URL` variable을 그 저장소로 바꾸면 됩니다. (또는 Cloudinary 같은 호스팅)

### 1-2. Instagram / Meta 준비 (기본: Instagram Login 방식)
1. 클리닉 인스타 계정이 **Professional(Business)** 계정인지 확인합니다 (프로필 편집에 "카테고리"가 보이면 이미 Professional).
2. https://developers.facebook.com/apps → Create App → 사용 사례 "Other" → 유형 **Business** → 생성.
3. 대시보드 → **Instagram → Set up** → "API setup with Instagram business login" 화면으로 들어갑니다.
4. 화면 안내대로 **Roles 탭 → Instagram Testers**에 클리닉 인스타 계정을 추가하고, 인스타 앱에서 초대를 수락합니다 (설정 → 앱 및 웹사이트 → 테스터 초대).
5. 다시 "1. Generate access tokens" → **Add account** → 클리닉 계정으로 로그인 → **Generate token** → 토큰 복사. 이게 `IG_ACCESS_TOKEN` (60일 장기 토큰) 입니다.
6. `IG_USER_ID`는 비워둬도 됩니다 (스크립트가 `me`로 호출). 웹훅(2번)·비즈니스 로그인(3번)·앱 리뷰(4번)는 본인 계정만 쓰는 한 필요 없습니다.

> 앱은 "개발 모드" 그대로 두세요. 테스터로 등록된 본인 계정에는 발행이 됩니다.

<details>
<summary>대안: Facebook Login 방식 (페이스북 페이지에 연결된 경우, 해시태그·인사이트 API까지 쓰려면)</summary>

1. 인스타 계정을 **Facebook 페이지에 연결** (프로필 편집 → Facebook → 연결).
2. 앱 대시보드 → Instagram → "API setup with Facebook login".
3. **Graph API Explorer**(https://developers.facebook.com/tools/explorer) → 앱 선택 → User Token, 권한 `instagram_basic`, `instagram_content_publish`, `pages_show_list`, `pages_read_engagement`, `business_management` → Generate → 로그인 시 페이지와 인스타 계정 체크.
4. `me/accounts?fields=name,instagram_business_account,access_token` 호출 → `instagram_business_account.id` 가 `IG_USER_ID`, 같은 블록의 `access_token`(페이지 토큰, 만료 없음)이 `IG_ACCESS_TOKEN`.
5. GitHub Variables에 `IG_API=facebook` 추가, Secrets에 `IG_USER_ID` 추가. 페이지 토큰을 쓰면 `refresh-token` 워크플로는 비활성화.
</details>

### 1-3. GitHub Secrets / Variables
저장소 → Settings → Secrets and variables → Actions

| 종류 | 이름 | 값 |
|---|---|---|
| Secret | `ANTHROPIC_API_KEY` | Claude API 키 |
| Secret | `IG_ACCESS_TOKEN` | 1-2의 5번에서 받은 장기 토큰 |
| Secret | `GH_PAT` | 매월 토큰 갱신 결과를 Secret에 다시 쓰기 위한 classic PAT (`repo` scope). GitHub → Settings → Developer settings → Personal access tokens |
| Secret | `IG_USER_ID` | Facebook Login 방식일 때만 |
| Secret | `FB_APP_ID`, `FB_APP_SECRET` | Facebook Login 방식 + 유저 토큰일 때만 |
| Variable | `IG_API` | 생략 시 `instagram`. Facebook Login 방식이면 `facebook` |
| Variable | `CLAUDE_MODEL` | 생략 시 `claude-sonnet-4-5`. 다른 모델 쓰려면 지정 |
| Variable | `PUBLIC_BASE_URL` | 생략 시 이 저장소의 raw URL. 별도 호스팅이면 지정 |

Settings → Actions → General → Workflow permissions 를 **Read and write** 로 바꿔야 봇이 커밋할 수 있습니다.

### 1-4. 첫 발행 테스트
1. Actions → **Daily publish** → Run workflow → `dry_run` 체크 → 실행. 로그에 URL/캡션이 찍히면 OK.
2. 샘플 `drafts/T-001-...json` 을 `approved/` 로 옮긴 뒤(아래 2-2) dry_run 없이 실행 → 실제 게시 확인.

---

## 2. 주간 운영 루틴

### 2-1. 자동 (건드릴 것 없음)
- **일요일 08:00** — `Weekly generate + render`: `topics.csv`에서 `pending` 3개를 뽑아 Claude로 초안 작성 → PNG 렌더링 → `drafts/`, `assets/` 커밋. 릴스 대본은 `reels/`에 md로 저장.
- **월–금 07:30** — `Daily publish`: `approved/`에서 `scheduled_date`가 오늘 이하(또는 비어 있음)인 것 중 가장 오래된 1개를 캐러셀로 발행하고, `story.png`를 스토리로 올린 뒤 `posted/`로 이동. 승인된 게 없으면 아무것도 안 합니다.
- **매월 1일** — 토큰 갱신 (Instagram Login 토큰은 60일 만료라 필요. Facebook 페이지 토큰이면 워크플로 비활성화).

### 2-2. 사람이 하는 일 (주 10분)
1. GitHub에서 `assets/<id>/` 폴더의 PNG를 눈으로 훑고, `drafts/<id>-*.json` 을 엽니다.
2. 문구 수정이 필요하면 GitHub 웹 편집기에서 JSON을 고치고 커밋 → `Re-render on edit` 워크플로가 PNG를 자동 재생성합니다.
3. 승인: 파일을 `drafts/` → `approved/` 로 옮깁니다. GitHub 웹에서는 파일 편집 화면의 파일명 칸에서 `drafts/T-001-...json` 을 `approved/T-001-...json` 으로 바꿔 커밋하면 됩니다. 특정 날짜에 올리고 싶으면 JSON의 `"scheduled_date": "2026-10-03"` 를 채워 두세요.
   - 로컬이면: `python scripts/approve.py T-001 --date 2026-10-03`
4. `topics.csv` 에 새 주제를 계속 추가합니다 (한 줄 = 한 게시물). `status`는 `pending`으로.

주 3개 생성 / 주 2~3개 승인 정도면 백로그가 자연스럽게 쌓입니다. 릴스는 `reels/*.md` 대본으로 월 1회 몰아서 촬영하고 캡션은 그대로 복사해 쓰면 됩니다.

---

## 3. 로컬 실행 (선택)

```bash
pip install -r requirements.txt
python -m playwright install chromium
cp .env.example .env   # 값 채우기

python scripts/generate.py --count 3        # 초안 생성 (--dry-run: 프롬프트만 출력)
python scripts/render.py                    # PNG 렌더링 (assets/<id>/preview.html 로 브라우저 미리보기 가능)
python scripts/approve.py --list
python scripts/approve.py T-001
python scripts/publish.py --dry-run
```

Windows PowerShell에서는 `.env` 대신 `$env:ANTHROPIC_API_KEY="..."` 식으로 설정하세요. 한글 출력 깨지면 `python -X utf8 scripts/...`.

---

## 4. 커스터마이즈

| 바꾸고 싶은 것 | 파일 |
|---|---|
| 색상, 폰트, 로고 텍스트, 지점, 푸터 문구, 면책 문구 | `config/brand.json` |
| 서비스별 색상 · 말투 · 주제 힌트 | `config/services.json` |
| 금지어 · 컴플라이언스 규칙 | `config/compliance.md`, 그리고 `scripts/generate.py`의 `banned` 정규식 |
| 전체 톤, 캐러셀 구조, 해시태그 규칙 | `style/voice.md` |
| 카드 디자인 | `templates/carousel.html` (수정 후 `python scripts/render.py --all`) |
| 생성 개수 · 발행 시간 | `.github/workflows/*.yml` 의 cron (UTC 기준. AEST = UTC+10, AEDT = UTC+11) |

로고 이미지를 넣고 싶으면 `templates/` 에 PNG를 두고 `carousel.html`의 `.logo` 부분을 `<img>`로 바꾸면 됩니다.

---

## 5. 자주 나는 문제

- **`Asset not publicly reachable`** — 저장소가 Private이거나 assets 커밋이 아직 안 된 상태. Public 전환 또는 `PUBLIC_BASE_URL` 확인.
- **`(#10) Application does not have permission`** — 토큰 권한에 `instagram_business_content_publish`(Instagram Login) / `instagram_content_publish`(Facebook Login) 누락, 또는 계정이 앱 테스터로 등록 안 됨.
- **`Invalid OAuth access token`** — 토큰 만료(60일). `Refresh Instagram token` 워크플로를 수동 실행하거나, 만료 후라면 대시보드에서 Generate token 다시.
- **`Media ID is not available` / 컨테이너 ERROR** — 이미지 URL이 이미지가 아니거나(HTML 반환) 비율이 허용 범위 밖. 템플릿은 4:5(1080×1350)와 9:16 스토리로 고정되어 있으니 URL 문제일 가능성이 큼.
- **토큰 만료** — 페이지 토큰으로 바꾸거나 `Refresh Instagram token` 워크플로를 수동 실행.
- **Actions에서 커밋 실패** — Workflow permissions가 Read and write인지 확인.
- **API 발행 한도** — 계정당 24시간에 최대 50건. 하루 1~2건 구조라 문제 없음.
