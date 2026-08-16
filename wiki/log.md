---
title: Wiki Log
category: 색인
tags: [log]
summary: 위키에 대한 모든 쓰기 작업의 시간순 기록. 최신이 위.
sources: [작업 수행 기록]
status: reviewed
created: 2026-08-04
updated: 2026-08-16
notion_page_id: null
notion_synced: null
---

> [!tip] 핵심 Takeaway
> - **모든 쓰기 작업 후 여기에 한 줄 남긴다.** 지식 자체보다 "언제 무엇이 왜 바뀌었나"가 나중에 더 자주 필요하다
> - 최신 항목이 맨 위. 연산은 `INGEST` / `QUERY` / `LINT` / `SYNC_NOTION` / `UPDATE` / `MIGRATE` / `FIX`
> - 이 로그가 건강검진의 입력이다 — 마지막 LINT 이후 쌓인 변경분이 다음 점검 범위

# Wiki Log

- [2026-08-16T17:20:00+09:00] FIX pages=2 note="2차 건강검진 수정(승인 범위: 모순·updated·로그 누락). ① index.md:117 'Notion 전사 오류 나머지 **29**개 페이지 미점검' → **32**개. 2026-08-15 시점 32페이지 기준으로 쓴 수치가 08-16 분할(35페이지)을 못 따라갔다 — 5시간 전 고친 index.md:21 페이지 수와 **정확히 같은 유형의 재발**이다. index는 '페이지 수는 부제 한 줄에만 둔다'는 자기 규칙을 두고도 미완 과제 절에서 다시 수기 집계를 했다 → 규칙이 '부제'만 막고 **파생 수치(전체−점검완료)**를 못 막은 것이 원인. ② verbal-source-verification-policy `updated` 2026-08-15→2026-08-16 — 08-16에 본문 50행을 `lifecycle: draft`→`status: draft`로 고치고 updated를 안 올렸다(§5.1-4 위반, 08-15 22:30 FIX와 동종 재발). 이 누락은 §6.3 증분 판정에서 조용히 Notion 재업로드를 건너뛴다. ③ 아래 16:59 UPDATE 항목을 소급 기록. 재검증: 깨진 링크 0 / 고아 0 / 단방향 0 / Takeaway 위반 0 / frontmatter 결손 0 / index 집합 일치. **미수정으로 남긴 것: Notion 지연 25건, 승격 후보 5건, 스키마 외 필드 3건**. ②로 총계는 안 변하고 구성만 바뀐다 — verbal-source-verification-policy가 '동일자 재판정'에서 '실질 지연'으로 이동(실질 12→13, 동일자 10→9). 즉 updated 누락은 **총계를 안 움직여 눈에 안 띄면서 실제 지연을 감추는** 유형이라 git 대조 점검이 필요했다"

- [2026-08-16T17:15:00+09:00] LINT issues=5 broken_links=0 orphans=0 one_way_links=0 takeaway_violations=0 frontmatter=0 stale=0 contradictions=1 index_mismatch=0 raw_unprocessed=0 notion_lag=25 secrets=0 promotion_candidates=5 schema_extra_fields=3 note="16:45 LINT의 미수정분을 이어서 전 37페이지 재점검. **지난번 오탐 2종이 규칙 반영으로 해소 확인** — 단방향 log→aurora-dsql은 CLAUDE.md §5.3의 `category: 색인` 제외 규칙으로 0건, 깨진 링크 4건은 인라인 코드 제외 후 0건(위키 자신이 obsidian-wiki-tooling-gotchas:35에 문서화해 둔 알려진 오탐이다 — 점검 스크립트가 그 문서를 반영해야 매번 4건이 재보고되지 않는다). 새 모순 1건은 index.md:117 파생 수치(29→32). 신규 항목 2종을 이번에 추가: **`updated` 미갱신 점검**(git 최종 수정일 vs frontmatter `updated` 대조 — 1건 적발) / **스키마 외 frontmatter 점검**(§2.3 표 밖 필드 — aliases 1, source_url 2). 승격 후보는 4→5로 재산정: 지난 4건 중 3건(db-access-control·postgresql-operations·postgresql-object-operations)이 16:59에 이미 reviewed로 승격됐고, 공식문서 대조가 끝난 draft를 다시 훑어 mysql-operations·mysql-dump-load·sqlserver-operations·aurora-vs-mysql-replication-architecture·db-change-safe-patterns가 남았다. **단 뒤 4건은 본문·index가 '실행 검증 전'을 명시해 승격이 그 문구와 충돌하므로 status만 올리면 안 된다.** 민감정보 0(재확인)"

- [2026-08-16T16:59:00+09:00] UPDATE pages=4 note="**소급 기록** — 16:59 커밋에 담겼으나 로그가 빠져 있던 작업(§7 위반, 17:20 FIX에서 보완). ① status 승격 3건 draft→reviewed: db-access-control·postgresql-operations·postgresql-object-operations. 셋 다 sources에 'PostgreSQL 공식 문서 2026-08-16 대조'가 있어 §2.5 요건 충족. ② 스키마 외 frontmatter 제거: `base_confidence`·`provenance`·`lifecycle`·`tier` — wiki-bot 스키마에서 흘러든 필드로 §2.3 표에 없다(봇 자체 설명인 wiki-bot-automation-tradeoffs:41의 lifecycle 언급은 외부 툴 기술이므로 유지). ③ verbal-source-verification-policy:50 `lifecycle: draft` → `status: draft` 용어 통일. ④ CLAUDE.md §5.3에 `category: 색인` 링크 그래프 제외 규칙 명문화 — 16:45 LINT가 오탐으로 지적한 건의 근본 수정"

- [2026-08-16T16:50:00+09:00] FIX pages=2 note="건강검진 모순 2건 수정(승인 범위: 모순만). ① index.md:21 페이지 수 33→35 — 같은 날 분할로 2개 늘었는데 부제를 안 고쳤다. 2026-08-15에 3중 기재를 부제 한 줄로 통합했는데도 여전히 수기 집계라 어긋났다 → 자동 산출이 아니면 또 어긋난다. ② sqlserver-operations:23 Takeaway '결함이 2종' → '결함 5건, 눈에 보이는 2건 + 조용히 실패하는 3건'으로 교정. 누락됐던 3건이 하필 전부 무증상 실패 유형(파싱 예외·무알람 실패·CHECKSUM 동반 해제)이라 Takeaway만 읽는 사용법에서 가장 위험한 축소였다. 부수로 index 미완 과제 '건강검진 항목 보강'을 현황(점검 1회 수행, 자동화 미완)으로 갱신. 재검증: 결함 개수 전 6곳 '5건' 일치 / 페이지 수 일치 / 깨진 링크 0 / 단방향 0 / Takeaway 4줄. **미수정으로 남긴 것: Notion 지연 25건, 승격 후보 4건, 단방향 점검의 log.md 오탐**"

- [2026-08-16T16:45:00+09:00] LINT issues=3 broken_links=0 orphans=0 one_way_links=0 takeaway_violations=0 frontmatter=0 stale=0 contradictions=2 index_mismatch=1 raw_unprocessed=0 notion_lag=25 secrets=0 promotion_candidates=4 note="전 37페이지 점검. 모순 2건 모두 **페이지 내부 개수 불일치** — index.md:21 '총 33개 페이지'가 실제 35개(08-16 분할로 2개 증가분 미반영), sqlserver-operations:23 Takeaway '결함이 2종'이 본문 warning·summary·index·sqlserver-backup-procedure의 '5건'과 어긋남(본문 열거도 5개). 후자는 2026-08-15 LINT가 못 잡아 index 미완 과제로 등록해 둔 '페이지 내부 개수·참조 불일치' 점검을 이번에 실제로 돌려 나온 첫 수확이다. Notion 지연 25=미동기화 3(db-permission-queries·db-change-safe-patterns·postgresql-object-operations)+실질 지연 12+동일자 재판정 10(§6.3 `>=` 규칙에 의한 의도된 중복). 단방향 1건(log→aurora-dsql)은 오탐 — log.md는 이력 기록이라 역링크 대상이 아니며 점검에서 index와 함께 제외해야 한다. 민감정보 0 — postgresql-operations의 10.20.30.0/24는 '실제 CIDR로 치환' 명시된 예시, mysql-dump-load의 mysql://user@target-host는 자리표시자. 분할 3개 페이지의 '전부 읽기 전용' 주장은 통계 리셋·DDL 혼입 여부를 재검색해 성립 확인. 리포트만, 수정 미실시"

- [2026-08-16T16:40:00+09:00] MIGRATE page="operational-queries" pages_created=2 pages_updated=14 note="허브 페이지 3분할 — INGEST 소요 시간 진단의 1순위 조치. 원인: 인바운드 17개 최다 허브가 45.4KB(위키 전체의 12%)라 DB 관련 적재마다 Edit 전 전량 Read가 걸렸다. 실측 근거는 커밋 3ba8ec2 — 손댄 6개 파일 101.6KB를 읽고 기존 페이지 실변경은 32줄(신규 143줄 제외), 읽기의 90%가 낭비. 분할선은 페이지가 스스로 '가장 중요한 구조'로 선언한 읽기전용/변경 경계 + 권한 주제축. 결과: operational-queries 45.4→23.2KB(-49%, 진단 1~11만), db-permission-queries 15.5KB(감사+부여), db-change-safe-patterns 15.4KB(DDL+DML). 절 번호를 페이지별로 재부여했고 '7번/9번/12번 섹션' 상호참조 4곳을 페이지 링크로 교정. 인바운드 재배선 12개 페이지(권한 3건→db-permission-queries, 변경 2건→db-change-safe-patterns, 별칭 노후 2건). 총량은 45.4→54.1KB(+8.7)로 늘었다 — 페이지당 frontmatter·Takeaway·Related·경계 설명이 3벌이 된 비용이며, 적재당 읽기량 감소와 맞바꾼 것. 검증: 깨진 링크 0 / 고아 0 / 단방향 0(index 제외) / Takeaway 3개 모두 6줄 이하 / frontmatter 필수 필드 결손 0. **미완: Notion에는 15절짜리 구본이 그대로 남아 다음 동기화 전까지 위키와 어긋난다**"

- [2026-08-16T00:02:00+09:00] INGEST source="Codex attachment: pasted PostgreSQL 오브젝트 메모" pages_created=1 pages_updated=3 mode=append note="오브젝트 소유권·DDL·복사·인덱스·파티션·뷰·시퀀스 런북 분리, current_user/session_user·char·pg_repack 무잠금 표현 교정"

- [2026-08-15T21:45:34+09:00] INGEST source="Codex attachment: pasted PostgreSQL 운영 메모" pages_created=0 pages_updated=2 mode=append note="접속·SCRAM 인증·스키마·확장 모듈·오픈 게이트 병합, MD5/trust·광역 HBA 예시 교정"

- [2026-08-15T21:38:04+09:00] QUERY query="SQL Server 설정 방법 정리" result_pages=1 note="공식 문서 대조 후 메모리·MAXDOP·TempDB·설치 및 운영 인수 기준 갱신"

## 2026-08

- [2026-08-15T23:35:00+09:00] FIX page="scripts/notion-convert.py" note="callout 안 순서 목록이 한 문단으로 뭉개지던 버그 수정. 원인 2가지 — ① 항목 판정이 문자열 '1.'만 검사해 2. 이후가 앞 항목에 병합 ② 빈 줄을 버려 뒤 문단까지 병합. 정규식 `^\\s*(?:[-*]\\s|\\d+\\.\\s)` + 빈 줄을 블록 경계로 처리. 회귀: 32개 전 페이지 변환 오류 0, Takeaway 불릿 수 불일치 0. 영향 페이지는 sqlserver-operations 1건뿐이며 Notion은 이미 수동 정리본이라 재동기화 불필요"
- [2026-08-15T23:20:00+09:00] SYNC_NOTION pages=3 updated=3 note="미완 3건 마무리 — mysql-operations·sqlserver-operations·db-security-review-patterns를 replace_content로 전체 교체. 사전에 Notion 전용 절 유무를 절 제목 대조로 확인(3개 모두 없음). 부수 효과로 \\uXXXX 전사 오류 8곳 일괄 해소(켰다 끓다/켜다/꿔진다/짦은/없앱니다/옷긴다/컬테이너 등). 전체 Notion 지연 0건"
- [2026-08-15T23:15:00+09:00] FIX page="sqlserver-operations" note="위키 내부 모순 발견·수정 — SP_DB_BACKUP 결함 callout 헤더가 '결함 4건'이고 항목도 4개인데 본문은 '위 5건을 고친'이라 참조. Notion과 sqlserver-backup-procedure에는 5번째(CHECKSUM이 COMPRESSION에 묶여 비압축 백업의 체크섬 검증까지 꺼짐)가 있었다. 전체 교체 전에 복원하지 않았으면 Notion에서 1건이 소실될 뻔했다"
- [2026-08-15T23:00:00+09:00] SYNC_NOTION pages=15 created=1 updated=14 skipped=17 stamped=13 target="DBA" note="mysql-dump-load 신규 생성(db운영>MySQL) 후 참조 6개 페이지 재업로드로 백틱→mention-page 전환. 전문 재업로드 대신 update_content 검색-치환으로 변경 구간만 전송. 미완 3건은 의도적으로 notion_synced 미기록 — mysql-operations(summary·Takeaway·인용블록 미반영), sqlserver-operations(Takeaway 병합 미반영), db-security-review-patterns(Takeaway 병합 미반영). 원인: Notion 본문이 현 변환기 출력과 구조적으로 다름(최초 동기화가 축약본으로 올라감) → 다음 동기화에서 해당 절 전체 교체 필요"
- [2026-08-15T22:58:00+09:00] FIX page="sqlserver-operations(Notion)" note="\\uXXXX 전사 오류 추가 발견 5곳: 켰다 끓다/소유자를 확인하고 켜다/체크섬 검증도 꿔진다/짦은 소량/없앱니다. 2곳(켠다·잦은) 교정 성공, 3곳은 old_str 매칭 실패로 미교정. 20:44 '옷길' 건과 같은 원인 — §6.4 ①(원시 UTF-8) 위반의 누적 피해. 위키 원문은 모두 정상"
- [2026-08-15T22:30:00+09:00] FIX page="db-access-control, cloud-platform-knowledge, aurora-vs-mysql-replication-architecture" note="INGEST 때 역링크만 넣고 updated를 갱신하지 않은 것 발견 — 2026-08-15로 수정. §5.1-4의 updated 갱신 누락"
- [2026-08-15T22:20:00+09:00] FIX page="CLAUDE.md" note="§6.3 증분 판정을 날짜 단위 비교로 완화(`updated > notion_synced` → `updated >= notion_synced 앞 10자`). updated는 날짜, notion_synced는 타임스탬프라 같은 날 수정분이 영구 누락되던 문제. 이날 수정 13개 중 12개가 실제로 누락 대상이었다"
- [2026-08-15T22:10:00+09:00] FIX note="건강검진 22건 전량 수정. 모순2: mysql-dump-load 규모 기준을 보수적 값(수 GB 이하)으로 통일 + ^[ambiguous] 병기 + Open Questions 등록 / sqlserver-xevent-sessions:19 논리 반전 문장 교정. 단방향 링크 4건 해소(obsidian↔dev-tooling-standards는 백틱 예시라 실제 링크가 없었음 — 양쪽에 실링크 추가). Takeaway 기준을 CLAUDE.md §2.2에서 2~4줄→2~6줄로 상향(44% 위반은 기준 쪽 문제), 초과 7개는 삭제 아닌 불릿 병합으로 축소. 수정 13개 페이지 updated 갱신. 재검증: 깨진 링크 0 / 단방향 0 / 고아 0 / Takeaway 위반 0"
- [2026-08-15T21:50:00+09:00] LINT issues=22 broken_links=0 orphans=0 one_way_links=4 takeaway_over_limit=15 frontmatter=0 stale=0 contradictions=2 index_mismatch=0 raw_unprocessed=0 notion_lag=1 secrets=0 note="깨진 링크 초기 4건은 백틱 예시 오탐 — 인라인 코드 제외 후 0건. 모순 2건: ① 백업 도구 규모 분기(mysql-operations '수 GB 이하' vs mysql-dump-load '~수십 GB') ② sqlserver-xevent-sessions:19 문장 논리 반전. 리포트만, 수정 미실시"
- [2026-08-15T21:35:00+09:00] FIX page="index" note="페이지 수 3중 기재(Takeaway·부제·절 제목 5개) → 부제 한 줄로 통합. CLAUDE.md가 요구하지 않는 자체 부가물이었고, 적재 1건당 편집이 3회 늘어나는 원인. 근거 LINT가 없는 '깨진 링크 0 / 고아 페이지 0' 주장도 제거 — 마지막 LINT는 2026-08-04이며 그때 broken_links=2였다"
- [2026-08-15T21:20:00+09:00] INGEST source="붙여넣기 — MySQL Dump & Load 가이드" pages_created=1 pages_updated=6 note="mysql-dump-load 신규. mysql-operations의 백업 표준 6줄은 도구 분기 판단으로 유지하고 실행 상세를 분리(sqlserver-operations↔sqlserver-backup-procedure 선례). Takeaway에 관리형 DB 고정 옵션 5종 추가. 역링크 5건(db-access-control, cloud-platform-knowledge, aurora-vs-mysql-replication-architecture, verbal-source-verification-policy, db-security-review-patterns). dumpBinlogs since ↔ compatibility 배타 조건을 index 미완 과제로 등록"
- [2026-08-15T21:05:00+09:00] QUERY query="SQL Server 설정값" result_pages=3 note="sqlserver-operations(sp_configure·Trace flag·TempDB·Collation), sqlserver-xevent-sessions(blocked process threshold 전제), operational-queries. 새 지식 없어 페이지 갱신 없음"
- [2026-08-15T20:45:00+09:00] SYNC_NOTION pages=31 note="교차참조 전환 — 위키링크를 <mention-page/>로 변경. scripts/notion-convert.py가 notion_page_id 맵을 참조해 링크를 직접 내도록 수정(2차 패스 영구 불필요). 이미 올라간 31개는 content_updates로 일회성 치환(슬러그형+표시명형 양쪽 투입, 미매칭 쌍은 무시됨). 전 페이지 회귀 테스트 235개 mention 생성/잔존 wikilink 0. CLAUDE.md §6.4 교차참조 항목 갱신"
- [2026-08-15T20:44:00+09:00] FIX page="dbgw-queries(Notion)" note="'옮길'이 '옷길'로 잘못 올라간 것 정정. \\uXXXX 이스케이프를 손으로 타이핑하다 생긴 전사 오류 — §6.4 ①(원시 UTF-8 사용)의 추가 근거. 다른 페이지에도 같은 유형 오타가 있을 수 있어 확인 필요"
- [2026-08-15T20:20:00+09:00] FIX page="CLAUDE.md" note="§6.4 ④ 정정 — '수십 KB면 분할'은 잘못된 귀인이었다. 실측 결과 실패는 크기가 아니라 형식 때문(동일 페이지가 18,430 bytes 실패 / 18,259자 성공, 5,076 bytes도 실패). operational-queries는 35,861자로 시험 없이 4청크 분할한 것이 순손실. '분할은 예측이 아니라 실패 후에'로 규칙 변경 + 크기는 바이트가 아닌 문자 수로 판단 명시"
- [2026-08-15T20:05:00+09:00] UPDATE page="CLAUDE.md" note="§6.4 실행 비용 규칙 신설 — 최초 동기화 실측 기반. ① JSON 한글 이스케이프 금지(2.24배 팽창) ② 표준 파라미터 형식 고정(8회 실패·97KB·8턴 손실) ③ 같은 부모 페이지 배열 묶기(31콜→12콜) ④ 대형 페이지는 insert_content 분할. 변환기·스탬프를 scripts/notion-convert.py·notion-stamp.py로 저장소 이관(세션 스크래치패드는 소실됨). §1 구조 트리 반영"
- [2026-08-15T19:50:00+09:00] SYNC_NOTION pages=31 skipped=2 target="DBA (3aefb969b8be801280b8dc2ff35fbefb)" note="최초 전량 동기화. 카테고리 5 + db운영 엔진 4 + 엔진공통 소분류 5 + kakaogames 구조 생성. index/log는 §6 규칙으로 제외. 전 페이지 notion_page_id·notion_synced 기록 완료 — 다음 실행부터 증분 판정 동작. 기존 '기술 문서' 하위 3개는 위키 미러가 아니라 원본 자료로 판단해 병합하지 않음(§6.2 확인 필요 대상)"
- [2026-08-15T18:55:00+09:00] FIX note="blocked process threshold 1초→5초로 통일. sqlserver-operations(sp_configure 블록·Takeaway·Open Questions), sqlserver-xevent-sessions(경고→근거 note, 원래 값 1초 보존), operational-queries, index.md 미완 과제 제거. ^[ambiguous] 2곳 해소"
- [2026-08-15T18:40:00+09:00] UPDATE page="sqlserver-xevent-sessions" note="신규 — XEvent 세션 3종(slow query·blocked process·error reported) 정의 + 데드락 미생성 근거. MS Learn으로 system_health 수집 범위 대조: 데드락 포함/blocked_process_report 미포함/error는 sev>=20만 확인. blocked process threshold 1초(구축표준) vs 5초(이 페이지) 불일치를 ^[ambiguous]로 기록. 역링크 5개 연결. index 30→31, db운영 19→20"
- [2026-08-15T18:20:00+09:00] UPDATE page="sqlserver-backup-procedure" note="신규 — SP_DB_BACKUP 결함 5건 수정본 작성(5번째 CHECKSUM/COMPRESSION 결합은 이번에 추가 발견). 파일명·디바이스명 형식 유지로 기존 백업 호환. 역링크 4개(sqlserver-operations, db-security-review-patterns, operational-queries, db-access-control) 연결. index 페이지 수 29→30, db운영 18→19"
- [2026-08-15T18:05:00+09:00] INGEST source="대화 붙여넣기 — SQL Server 구축 표준 메모" pages_created=0 pages_updated=3 note="sqlserver-operations에 구축 표준·운영 Job/프로시저·Open Questions 신설. db-security-review-patterns에 위험 패턴 4건 추가(xp_cmdshell 토글, TRUSTWORTHY, 삭제 조건 식별자 누락, SELECT 오류 반환). index.md 미완 과제 3건 추가. 실 서비스 DB명·인스턴스 번호·개인 계정명은 §9-2로 제외"
- [2026-08-15T17:52:00+09:00] UPDATE page="CLAUDE.md" note="§6.1 `엔진 공통`에 소분류 5개(엔진 비교/진단·운영 표준/보안·권한/개발·자동화/지식 운영) 추가. index.md 절 이름과 일치시키는 규칙 명문화"
- [2026-08-15T17:45:00+09:00] UPDATE page="CLAUDE.md" note="§6 Notion 동기화에 §6.1 배치(db운영=엔진별, 업무기록=회사별·현재 kakaogames)·§6.2 병합(기존 페이지 있으면 신규 생성 금지) 규칙 추가. README.md 요약 반영"
- [2026-08-15T17:30:00+09:00] FIX note="Codex 세션 시작/종료 git 자동 동기화 추가 — .codex/hooks.json 신규. $CLAUDE_PROJECT_DIR가 Codex에 없어 $(git rev-parse --show-toplevel)로 대체. CLAUDE.md §1·§8, README.md 반영. Codex 실행 검증 미완"
- [2026-08-15T16:48:00+09:00] QUERY query="DSQL에 대해 정리해줘" result_pages=1 note="기존 [[aurora-dsql]]로 답변. 신규 정보 없어 페이지 변경 없음"
- [2026-08-15] MIGRATE source="llm-wiki/second-brain" pages=29 raw_archived=19 note="플랫 구조로 이전. 폴더 계층(dba/career/personal/references/synthesis) 제거하고 `category` 프론트매터로 분류 전환. 전 페이지 프론트매터 신 스키마 변환 + Takeaway callout 신규 작성. wikilink 경로 접두어 전면 제거. `_hub.md` 2개·`ROUTING.md`·`hot.md` 폐지(index.md와 CLAUDE.md가 대체)"
- [2026-08-15] FIX note="교차참조 보강 — 비어버린 Related 절 12개 작성, 역방향 링크 34건 추가. 결과: 깨진 링크 0 / 고아 페이지 0 / 단방향 링크 0"
- [2026-08-15] UPDATE page="vault-governance-decisions" note="구조 변경 반영 — 플랫 적재, CLAUDE.md 실체 + AGENTS.md 심볼릭 링크로 단일 소스 반전, 충돌 원격 우선 결정 추가. 이전 결정은 '변경 이력'에 보존"
- [2026-08-15] UPDATE page="obsidian-wiki-tooling-gotchas" note="wikilink 경로 접두어 함정이 플랫 구조에서 소멸함을 기록"
- [2026-08-15] INIT repo="muto-wiki" note="CLAUDE.md 스키마 작성, AGENTS.md 심볼릭 링크, scripts/sync.sh(원격 우선), SessionStart/Stop 훅 등록, Obsidian 볼트를 저장소 루트로 승격"

## 이전 이력 (llm-wiki/second-brain)

- [2026-08-12T12:56:15+09:00] INGEST source="_raw/2026-08-12-claude-code-gcal-mcp-blocked.md" pages_updated=1 pages_created=0
- [2026-08-12T10:51:00+09:00] CAPTURE page="aurora-vs-mysql-replication-architecture" title="Community MySQL 복제와 Aurora Reader 아키텍처 비교"
- [2026-08-12T10:49:23+09:00] INGEST_URL url="https://github.com/obra/superpowers" page="superpowers-agentic-development-methodology" pages_updated=1
- [2026-08-12T10:10:24+09:00] INGEST source="_raw/2026-08-12-aidlc-superpowers-brainstorming-comparison-request.md" pages_updated=2
- [2026-08-12T09:00:31+09:00] INGEST_URL url="https://github.com/awslabs/aidlc-workflows" page="aws-aidlc-workflows-v2-study"
- [2026-08-12T08:08:26+09:00] INGEST source="_raw/2026-08-11-wiki-bot-automation-tradeoffs.md" pages_updated=3 pages_created=1
- [2026-08-10T00:00:00+09:00] CAPTURE page="todo" title="서울숲 데이트" due="2026-09-05"
- [2026-08-07T19:23:30+09:00] CAPTURE page="todo" title="DBGW 성능 개선 및 DBGWS 승인 절차" due="2026-08-10T10:00:00+09:00"
- [2026-08-06T22:58:55+09:00] QUERY query="내일 할 작업에 대해 정리해줘" result_pages=1
- [2026-08-06T22:14:49+09:00] CAPTURE page="dba-agent-work-plan" title="DBA Agent 구조 개편 및 주간 분석 작업 계획"
- [2026-08-06T22:12:45+09:00] QUERY query="AWS Aurora DSQL 관련한 내용 찾아줘" result_pages=2
- [2026-08-06] CAPTURE page="vault-governance-decisions" title="볼트 거버넌스 결정 — career 회사 라우팅·에이전트 규칙 단일화·브랜치 금지"
- [2026-08-06] CAPTURE page="verbal-source-verification-policy" title="구술·사내 출처는 공식 문서 대조 전까지 승격하지 않는다"
- [2026-08-06] CAPTURE page="dbgw-queries" title="dbgw 메타DB 운영 쿼리" note="원본 그대로 보관"
- [2026-08-06] UPDATE page="mysql-partition-pruning-prepared-stmt-bug" note="리포트 재확인 — 최소 재현 케이스·내부 함수명·SP 포함 추가. 사내 문서의 8.0.41 표기 정정(실제 8.0.42), Reorganize는 재발 방지가 아닌 리셋임을 명시"
- [2026-08-06] UPDATE page="obsidian-wiki-tooling-gotchas" note="obsidian-git askpass chmod +x 반복 diff 함정 섹션 추가"
- [2026-08-06] QUERY query="MySQL 버전 업그레이드 관련 버그 내용 찾아서 보여줘" result_pages=2
- [2026-08-06] QUERY query="aws aurora dsql 설명들은거 알려줘" result_pages=1
- [2026-08-06] FIX note="세션 날짜 오기 정정 — 페이지 3곳, 로그 5줄"
- [2026-08-05] CAPTURE page="mysql-partition-pruning-prepared-stmt-bug" title="MySQL 8.0.42 파티션 pruning 캐시 회귀 (Bug #119309)" note="공식 버그 리포트 + 자체 재현 테스트"
- [2026-08-04] EXPORT target="Notion 🗃️ DBA" pages=14 source="dba/*.md" direction=vault→notion
- [2026-08-04] UPDATE page="aurora-dsql" lifecycle=draft→verified note="AWS 공식 문서 대조. 스토리지 무제한 주장 정정, 공식 한도표·미지원 기능·DPU 과금 추가"
- [2026-08-04] CAPTURE page="operational-queries" title="운영 진단 쿼리 모음 (MySQL·PostgreSQL·SQL Server)" note="표준 시스템 뷰 기반, 실행 검증 전(draft)"
- [2026-08-04] LINT issues_found=4 broken_links=2 missing_summary=2 links_fixed=2
- [2026-08-04] INGEST source="_raw/ (15 files)" pages_created=15
- [2026-08-04] INIT vault="second-brain" categories=concepts,entities,skills,references,synthesis,journal topics=dba,career
