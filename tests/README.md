# MINE:D 테스트

실제 브라우저(Chromium, Firefox, WebKit)에서 게임을 띄워 확인하는 회귀 테스트와 성능 측정 도구입니다.
게임 파일은 고치지 않습니다. 테스트용 로컬 서버가 `index.html`을 내줄 때만 게임 스크립트 끝에
`window.__ev = s => eval(s)` 한 줄을 끼워 넣어, 테스트가 게임 내부 상태를 읽고 함수를 부를 수 있게 합니다
(`harness.py`).

## 준비 (처음 한 번)

필요한 것: Python 3.9 이상, 인터넷 연결(브라우저 엔진 내려받기, 약 1.1GB).

```sh
# 저장소 루트에서
python3 -m venv .venv
.venv/bin/pip install -r tests/requirements.txt
.venv/bin/playwright install chromium firefox webkit
```

- Linux에서는 엔진이 쓰는 시스템 라이브러리도 함께 설치하세요: `.venv/bin/playwright install --with-deps chromium firefox webkit`
- Windows에서는 `.venv/bin/` 대신 `.venv\Scripts\`를 쓰세요.
- 엔진은 사용자 캐시 폴더(macOS `~/Library/Caches/ms-playwright`, Linux `~/.cache/ms-playwright`,
  Windows `%LOCALAPPDATA%\ms-playwright`)에 설치되고, 저장소에는 아무것도 생기지 않습니다(`.venv/`는 `.gitignore`에 있음).
- 시스템에 설치된 Chrome·Safari·Firefox는 쓰지 않습니다. WebKit은 Safari와 같은 엔진이지만 Safari 앱 자체는 아닙니다.

## 실행

```sh
.venv/bin/pytest tests --browser chromium                                     # 약 3분
.venv/bin/pytest tests --browser chromium --browser firefox --browser webkit  # 세 엔진, 약 12분
.venv/bin/pytest tests -k noguess --browser webkit                            # 이름으로 골라 실행
.venv/bin/pytest tests --browser chromium --headed                            # 브라우저 창을 띄워서 보기
```

`index.html`을 고친 뒤에는 `python3 build_langs.py`를 먼저 실행하세요. 언어별 페이지가 원본과 다르면
`test_language_pages_seo_and_play`와 `test_generated_pages_are_up_to_date`가 실패합니다.

## 무엇을 확인하나

| 파일 | 내용 |
|---|---|
| `test_game.py` | 첫 클릭 보호(7개 난이도 모든 칸, 실제 클릭, 지뢰가 많은 판), 추측 불필요 판 생성(풀이 재생 검증, 시간 초과, 페이지 쪽 제한 시간, Worker 오류·잘못된 응답 7종, Worker 없을 때 분할 생성, 취소·새 게임·난이도·모드 변경, 페이지 쪽 재검증 중 취소, 생성 중 R/H/N), 재시작 정책, 힌트(열린 0 옆 잘못된 깃발, 완전 탐색과 비교한 추론 정확성, 추측 필요 판정, 예산 초과 시 "추측 필요"라고 하지 않음, 분할 검사 결과 일치, 진행 표시와 이동 시 취소, 힌트만으로 추측 불필요 판 끝내기), 통계 귀속과 초기화, 편집 중 상태, 저장 데이터 검증과 재로드, 공유 코드 길이 검사, 접근성(격자 구조, 이름, 방향키, Enter/Space, 통계 창 포커스, ARIA 모델), 터치 열기/깃발 전환과 끌어서 스크롤, 언어별 페이지 SEO와 동작 |
| `test_features.py` | 플레이어 의견을 반영한 기능: 일시정지(시간 멈춤, 판 가림, 입력 차단, 탭 이탈 시 자동, P·F2), 3BV 계산(독립 구현과 300판 비교)과 승리 시 효율 줄·최고 3BV/s, 오늘의 판(날짜별 같은 판, 세 엔진 동일 지문, 첫 동작부터 시간, 기록·공유, `?daily` 링크, 재시작), 양쪽 버튼·가운데 버튼 코딩, 길게 눌러 깃발(누르는 중 표시, 움직이면 취소, 설정 저장, 터치 contextmenu 무시, Chromium 실제 터치), 앱 정보 파일과 오프라인 실행(Chromium) |
| `test_review.py` | 2026-11 점검에서 고친 것: 오늘의 판 저장값 검증(깨진 값이 있어도 판이 열리고 승리가 기록됨), 공유 창을 닫았을 때 오류 창이 뜨지 않음, 탭을 떠난 사이 만들어진 추측 불필요 판은 일시정지로 대기, 폰트 서버가 응답하지 않아도 게임이 시작되고 조각 작업 중에도 타이머가 돎, 키보드 사용자의 초점 유지(N·R, Tab으로 들어온 경우 포함)와 마우스 사용자에게는 초점 테두리 없음, 편집기(오늘의 판에서 열기, 확대·축소 키), 모든 컨트롤의 이름(4개 언어), 정보 패널 구조와 배치, 고른 색 모드와 브라우저 바 색, 휴대폰 메뉴 글자 대비 4.5:1, 터치 화면용 첫 방문 안내, 언어별 문구 누락 검사, 생성 파일(`en/` `ja/` `zh/` `sitemap.xml` `robots.txt`) 최신 여부, `set-domain.sh` 왕복 |
| `test_wishlist.py` | 플레이어 요청(오픈소스 지뢰찾기의 GitHub 이슈, Hacker News 토론)에서 고른 개선: 지뢰를 밟은 뒤 무르고 계속하기(판·깃발·시계 복원, 승리·기록·연승·오늘의 판 기록에서 제외), 연승(패배·중단 시 끊김, 통계 열, 저장값 검증), 마지막 난이도 기억(사용자 지정 포함, 잘못된 저장값 무시), 휴대폰 접이식 메뉴(판이 첫 화면에 보임, 손가락 크기 버튼, 접히는 조건)와 데스크톱 메뉴 유지, 기록 내보내기·가져오기(합치기 규칙, 같은 파일을 두 번 읽어도 같음, 다른 파일과 모르는 항목 거부), 판 전체에서 브라우저 우클릭 메뉴 차단, 추측이 필요할 때의 힌트(모든 지뢰 배치를 세어 본 값과 칸별 확률 비교, 큰 판에서 확률의 합이 지뢰 수와 일치, 가장 안전한 칸과 확률 표시, 깃발 꽂은 칸은 건너뜀). 깃발 모드의 첫 탭이 칸을 여는 것은 `test_game.py`의 `test_touch_open_flag_switch`가 확인 |
| `test_fair.py` | 추측 안전 모드: 찍을 수밖에 없는 자리에서 지뢰 칸을 열면 지뢰가 옮겨지고 판이 그대로 맞는지(숫자 옆 칸·숫자와 떨어진 칸, 열린 숫자·깃발·남은 지뢰 수 유지), 안전한 칸을 알아낼 수 있을 때와 확실한 지뢰를 열 때는 보호하지 않음(각각의 안내 문구, 무르기 가능), 숫자 주변 한 번에 열기(코딩)도 보호, 강제일 때만 찍는 플레이어는 26판 모두 지지 않음, 새 배치가 가능한 모든 배치 중에서 고르게 뽑히는지(모든 배치를 세어 본 값과 비교), 탐색 예산이 모자랄 때의 처리, 편집한 판·오늘의 판은 바꾸지 않음, R로 다시 하면 처음 배치로 돌아감, 힌트 문구, 메뉴·통계·기록 가져오기(4개 언어) |
| `test_compat.py` | 2026-10 수정 전 버전(커밋 `109b1da`)과 같은 게임 번호·첫 칸이면 같은 판이 나오는지(187개 조합, 추측 불필요 16개 포함), 공유 코드가 같은지, 공유 링크로 판이 열리는지. 기준값은 `fixtures/golden.json` |

엔진별로 빠지는 것:

- Chromium에서만: 실제 접근성 트리 확인(`test_accessibility_tree_names`, CDP 필요), 터치로 끌어 스크롤하기(CDP 제스처).
- Firefox·WebKit의 접근성은 Playwright가 계산한 ARIA 모델로만 확인합니다(`test_aria_model_all_browsers`). 엔진 자체의 접근성 트리와 실제 화면 낭독기(VoiceOver, NVDA 등)는 이 테스트로 확인되지 않습니다.
- 터치는 모두 에뮬레이션입니다. 실제 휴대폰은 확인하지 않습니다.

## 기준값 다시 만들기 (`fixtures/golden.json`)

판 생성 방식을 일부러 바꿨을 때만 다시 만드세요. 기존 게임 번호로 같은 판을 재현할 수 없게 됩니다.

```sh
.venv/bin/python tests/tools/make_golden.py              # 커밋 109b1da 기준 (git 필요)
.venv/bin/python tests/tools/make_golden.py --ref HEAD   # 다른 버전 기준
```

## 성능 측정 (`tools/perf.py`)

pass/fail 테스트가 아니라 수치를 보는 도구입니다. 실제 마우스·키 입력으로 80×50, 100×60 판에서 판 만들기,
새 게임, 첫 클릭, 힌트, 패배 공개, 6000칸 연쇄 열기, 추측 불필요 생성(Worker 있음/없음), 생성 중 입력을 반복해서 잽니다.

```sh
.venv/bin/python tests/tools/perf.py                                   # 현재 버전, Chromium, 시나리오마다 15회
.venv/bin/python tests/tools/perf.py --cpu 4 --cpu 6                   # CPU 4배·6배 느리게 (Chromium 에뮬레이션)
.venv/bin/python tests/tools/perf.py --mobile --cpu 4                  # 휴대폰 크기 터치 화면 + CPU 4배 (에뮬레이션)
.venv/bin/python tests/tools/perf.py --browser firefox --browser webkit
git archive 109b1da | tar -x -C /tmp/old                               # 비교할 옛 버전 꺼내기
.venv/bin/python tests/tools/perf.py --compare old=/tmp/old            # 같은 회차를 두 버전이 번갈아 실행
```

- 결과는 시나리오·지표마다 최솟값 / 중앙값 / p90 / 최댓값으로 출력되고, 원자료는 `tests/results/`(git 제외)에 JSON으로 저장됩니다.
- 지표: `input_to_paint`(입력 시각부터 처리 후 첫 프레임까지, 모든 엔진), `event_timing`(브라우저가 잰 입력→다음 그리기, Event Timing을 지원하는 엔진에서. 16ms 미만은 16으로 표시),
  `longest_task`(50ms 이상 작업, Chromium), `main_script/style/layout/paint`(Chrome 트레이스의 메인 스레드 시간, Chromium), `time_to_start`(추측 불필요 판 시작까지).
- 컴퓨터가 바쁘면 수치가 크게 흔들립니다. 버전끼리 비교할 때는 `--compare`를 쓰세요. 같은 회차를 번갈아 재므로 부하 변화가 양쪽에 똑같이 걸립니다.

### 분할 처리의 "8ms"는 목표입니다 (상한이 아님)

Worker를 쓸 수 없을 때 추측 불필요 판 생성, 페이지 쪽 재검증, 힌트의 완전 탐색은 `runSliced`가 조각으로 나눠 실행합니다.
한 조각은 8ms가 지난 뒤 처음 만나는 양보 지점(생성기의 `yield`)에서 끝납니다. 그래서 조각 길이는
"8ms + 진행 중이던 한 단계"이고, 한 단계가 길면 그만큼 넘칩니다. 단계는 짧게 유지합니다
(풀이 한 라운드는 경계 칸만 읽고, 완전 탐색은 4096단계마다 양보). 테스트 `test_noguess_without_workers_runs_in_short_steps`가
단계 길이의 p99가 8ms 미만인지, 최댓값이 100ms 미만인지 확인합니다(최댓값은 GC나 바쁜 컴퓨터 때문에 늘어날 수 있어 느슨하게 둡니다).
조각 사이의 화면 그리기와 입력 처리 시간은 여기에 포함되지 않습니다.

다음 조각은 브라우저에 작업 스케줄러가 있으면 `scheduler.postTask`의 낮은 우선순위(background)로, 없으면
`MessageChannel` 작업으로 예약합니다. `setTimeout(0)`은 연속 호출 시 4ms씩 쉬게 되어 평소에는 쓰지 않습니다.

다만 32ms마다 한 번은 다음 조각을 `setTimeout(0)`으로 예약해 타이머에게 차례를 줍니다. Firefox는 페이지가 아직
로딩 중일 때(느린 웹폰트만으로도) 타이머를 다른 모든 작업 뒤로 미루기 때문에, 조각이 길게 이어지면 시계와
"확실한 칸을 찾는 중…" 안내가 작업이 끝날 때까지 멈췄습니다. `test_game_plays_and_timers_run_while_the_font_server_hangs`가
폰트 서버가 응답하지 않는 상태에서 이를 확인합니다.
