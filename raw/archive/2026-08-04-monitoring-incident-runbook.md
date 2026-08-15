---
title: 모니터링·장애 대응 런북 — 임계치·시간박스 대응·점검 주기 (Notion 심층 수집)
tags: [dba, monitoring, incident-response, runbook]
topics: [dba]
summary: >-
  CloudWatch→PI→엔진 내부 뷰 감시 흐름, 시간박스형(5분/15분/근본) 장애 대응,
  엔진별 대표 시나리오, 일/주/월 점검 체크리스트, 백업·복구 계층.
project: second-brain
base_confidence: 0.8
provenance:
  extracted: 0.9
  inferred: 0.1
lifecycle_changed: 2026-08-04
sources:
  - "Notion: 운영 및 모니터링 트리 (https://app.notion.com/p/3adfb969b8be8110ac0dfc1398dec404, 2026-07-30)"
---

# 모니터링·장애 대응 런북

## 감시 흐름 표준

CloudWatch 알람 → Performance Insights(AAS/Top Wait/Top SQL) → 엔진 내부 뷰(DMV/P_S/pg_stat_*) → 슬로우 쿼리·실행 계획 → 조치.
**시효**: AWS PI 콘솔은 2026-07-31 종료 → CloudWatch Database Insights로 전환(API는 유지). "PI 화면" 기반 절차는 재검증 필요.

## 일반론 임계치 (반드시 기준선 보정)

CPU 지속 70%↑ 경고/85%↑ 위험 · FreeableMemory < 메모리 10% · Swap>0 지속 · 디스크 Latency>20ms 지속·IOPS 한도 80%↑ · 스토리지 여유<15% · 커넥션 max 80%↑ 지속 · ReplicaLag 1초↑ 지속 · blocked 세션>0 지속.

## 신규 클러스터 오픈 체크리스트

PI 활성화(보존 7일+) · Enhanced Monitoring 1~15초 · Slow/Error 로그 CloudWatch 발행 · 알람 세트(CPU/Freeable/Storage/Connections/ReplicaLag, PG는 MaximumUsedTransactionIDs·OldestReplicationSlotLag) · 파라미터 그룹 IaC · 백업/PITR 정책 · pg_stat_statements/performance_schema/Query Store 활성화 · Reader/Writer 엔드포인트 분리.

## 시간박스형 장애 대응

- **1차(5분)**: CloudWatch 4-up(CPU/FreeableMemory/FreeStorageSpace/Connections) + PI로 병목 레이어(CPU/IO/Lock/Network) 구분 + 최근 30분 변경 이력.
- **2차(15분)**: 내부 뷰 정밀 진단 + 단기 회피(세션 kill, 힌트, 인덱스, 업스케일). ※ kill 전 세션 식별·롤백 소요·재시도 폭주 사전 점검 필요 (원본에 누락된 부분).
- **3차(근본)**: Query Store/pg_stat_statements 시계열 회귀, 통계·vacuum·파라미터 영향, 재발 방지(알람 보강, IaC, 변경 게이트).

## 엔진별 대표 시나리오

- **MySQL Too many connections**: max_connections 공식 `{DBInstanceClassMemory/12582880}`, Sleep 다수=풀 누수, RDS Proxy 검토. Replica Lag: 병렬 적용(replica_parallel_workers, LOGICAL_CLOCK), 대량 DML 분할.
- **PG wraparound 경보**: 장기 트랜잭션 종료 → 미사용 슬롯 drop → `vacuumdb --freeze --jobs N`.
- **Aurora**: Backtrack(Aurora MySQL 한정, 최대 72h, **클러스터 생성 시 활성화 필요**), Clone=copy-on-write 테스트 분기, 페일오버 DNS TTL 5초 + 커넥션 검증. Aurora PG 페일오버 ≈30초.
- **RDS SQL Server**: 로그 백업은 RDS 관리지만 장기 트랜잭션 시 truncate 불가로 로그 폭증 → `DBCC OPENTRAN`.

## 점검 주기 체크리스트

- **일간**: 성능(CPU/Mem/IO/AAS/슬로우/풀스캔/Lock/커넥션풀), 복제 lag·오류, 백업 성공·checksum, Error/Slow/OS 로그, 이상 감지(spike, ETL 지연).
- **주간**: Top Slow 랭킹 트렌드, 미사용·중복 인덱스, autovacuum/analyze, 파티션 롤오버, retention, 계정·권한 변경 반영.
- **월간**: 용량 계획, 마이너 패치·deprecated 검토, **Full Recovery/PITR/DR failover 실전 테스트**, 미사용 오브젝트 정리, 권한 감사·TLS·마스킹 컴플라이언스.
- 인시던트 회고: 최초/누락 알람, RCA 가능 여부, 임시 vs 근본 분리, Runbook·알람·파라미터 갱신.

## Daily Report 인텔리전스 체계

일별 리포트 → 월간 통합 → 일별 원본 보관. 추적 대상: MySQL/PG/SQL Server 커뮤니티 + RDS/Aurora + Azure SQL MI 릴리스·버그·지원정책. (2026-07 예: MySQL 26.7.0 EA CalVer 전환, PostgreSQL 19 Beta 2, SQL Server 2016 지원 종료.)

## 발견된 위험 자료 (원본 교정 필요)

- 스크립트 페이지에 **TRUNCATE 문 일괄 생성기가 "DB 초기화"로 경고 없이 게재** — 실제 서비스 스키마명 잔존, 조회 쿼리와 혼재. 파괴 명령 분리 원칙 위반.
- `CALL sys.ps_truncate_all_tables(FALSE)`(통계 리셋)가 조회 쿼리 사이에 경고 없이 배치.
- 단위 라벨 오류(`/1e12`로 초 단위인데 '(ms)' 표기), 관행적 NOLOCK/READ UNCOMMITTED 힌트에 설명 없음.
- 체크리스트 항목에 확인 명령·임계 기준·조치 링크 부재 (예: "백업 checksum OK"의 검증 방법).
- Database Mail: 개인 이메일 잔존, principal `public`+default profile은 전체 사용자 메일 발송 허용 — 과도 권한.
