---
title: Notion 지식베이스 교정 백로그 (전체 뎁스 감사 결과)
tags: [knowledge-management, security, backlog]
topics: [dba]
summary: >-
  전체 뎁스 수집(~140페이지)에서 발견된 교정 대상 목록 — 위험 명령 무경고 게재,
  민감정보 잔존, 빈 페이지, 색인 드리프트. 우선순위 순.
project: second-brain
base_confidence: 0.85
provenance:
  extracted: 0.9
  inferred: 0.1
lifecycle_changed: 2026-08-04
sources:
  - "Notion: Muto - DBA 통합 포털 전체 뎁스 감사 (2026-08-04)"
---

# Notion 지식베이스 교정 백로그

전체 뎁스 수집(6개 영역, ~140페이지, fetch 실패 0)에서 발견. 우선순위 순.

## P1 — 위험 명령·민감정보 (즉시)

1. **TRUNCATE 일괄 생성기**가 "DB 초기화" 이름으로 경고 없이 게재 (오타 'trucate' 포함), 실제 서비스 스키마명 잔존 — 격리 + 스키마명 치환.
2. **mydumper 페이지에 실제 QA RDS 호스트명 노출** — placeholder 치환.
3. **Database Mail 문서에 개인 Gmail 주소 잔존** + principal `public`/default profile 과도 권한 — 제거·교정.
4. Docker `docker rm -f $(docker ps -aq)` 무차별 삭제 명령 무경고 — 고위험 격리.
5. 2023 my.cnf의 내구성 포기 설정(`innodb_flush_log_at_trx_commit=0`, `sync_binlog=0`, `innodb_doublewrite=0`, `skip_ssl`) — 경고 콜아웃 추가 또는 보관 격리.
6. `CALL sys.ps_truncate_all_tables(FALSE)`(통계 리셋)가 조회 쿼리와 혼재 — 상태 변경 명령 분리.

## P2 — 오류·구식 정보

7. MySQL 히트율 쿼리에 PG 전용 `FILTER (WHERE)` 문법 혼입 — 실행 불가.
8. `sys.sysprocesses WHERE blocked > 50` — blocked는 SPID, 임계치 아님 (오독 유발).
9. "RC는 읽는 로우에 S lock" — InnoDB MVCC와 상충하는 구식 서술.
10. Prometheus v2.1.0/Alertmanager v0.13.0 실습 — 0.0.0.0 바인딩 + `--web.enable-lifecycle` 위험, 보관 격리 필요.
11. MySQL 복제 문서에 8.0.22+ 신구문(`SHOW REPLICA STATUS`) 병기 없음.
12. 단위 라벨 오류(`/1e12` 초 단위인데 '(ms)' 표기), NOLOCK/READ UNCOMMITTED 힌트 무설명.
13. 인덱스 리빌드 스크립트: MAXDOP=0 고정·ONLINE 없음·임계 미기재 — 자동 실행 금지 명시 필요.
14. AWS 세미나 노트(2022~23)의 BabelFish 제약·PI 오버헤드 수치 — 현재 동작 재검증 전 `보관`.

## P3 — 구조·완성도

15. 빈 페이지: Real MySQL 8.0, Aurora MySQL, MySQL 5.7.24, DB별 사이즈 조회 — 채우거나 목록 제외.
16. Kafka는 PDF 첨부만 존재 — 본문 이관 필요. RDS 트러블슈팅 PDF 5종도 미증류.
17. 인코딩 깨진 한글·AI 대화 잔재 다수 페이지 — 교정.
18. KB 색인 드리프트: 실제 33건인데 포털 기록 31건, 검증완료 실측 19건 vs 보고서 17건, ID 32 결번, 원본 링크 누락 4건 — 재집계.
19. "발행일·대상 버전 기록" 규칙이 학습·참고 하위 어디에도 실적용 안 됨.
20. 체크리스트 항목에 확인 명령·조치 링크 부재. Slack Bot scope 과다 검토(+토큰 회전 절차 문서화).
