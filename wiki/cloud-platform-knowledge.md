---
title: 클라우드·플랫폼 지식 — Aurora 내부·Azure 백업·Linux·Docker
category: db운영
tags: [dba, aws, aurora, docker, azure, linux]
summary: Aurora 스토리지 내부 구조와 운영 특성, SQL Server→Azure Blob 백업 절차, Linux 점검 명령, Docker MySQL 실습 표준. AWS 세미나(2022~23) 지식은 재검증 필요.
sources: ["Notion: 클라우드 및 플랫폼 트리 (2026-07-30)", "AWS 세미나 노트 2022~2023 (보관 대상)"]
status: draft
created: 2026-08-04
updated: 2026-08-15
notion_page_id: "3bdfb969-b8be-81bd-b165-c9eedaa93e87"
notion_synced: "2026-08-15T22:55:00+0900"
---

> [!tip] 핵심 Takeaway
> - **Aurora는 swap을 쓰지 않는다 → 메모리 부족 시 RDS보다 다운 확률이 높다.** 인스턴스 사이징과 메모리 알람 기준을 RDS와 같게 두면 안 되는 이유
> - **Aurora parallel query는 buffer pool을 쓰지 않고 Storage Node에서 계산한다 → 비용이 급증할 수 있다.** 켜기 전에 과금 영향부터 확인
> - **일반 백업 절차에 `SET ENCRYPTION OFF` / `DROP DATABASE ENCRYPTION KEY`가 들어있으면 그건 사고다.** 승인·인증서 백업 없이 실행 금지 — [[db-security-review-patterns]]의 대표 사례
> - **`RESTORE VERIFYONLY`는 보조 수단일 뿐, 실제 복원 테스트가 최종 검증이다.** 백업 검증 자동화를 만들 때 여기서 멈추면 안 된다
> - **이 페이지의 Aurora 수치는 2022~23 세미나 기반이라 `보관` 등급이다.** 특히 PI 오버헤드 5~10%, BabelFish 제약 목록은 공식 문서 재확인 없이 인용하지 않는다 — [[verbal-source-verification-policy]]
> - **이미지 `latest` 태그를 쓰지 않는다.** InfluxDB `latest`가 2026-09-15부터 메이저 버전을 갈아타는 것이 실증 사례 — 인증·API가 통째로 바뀐다

# 클라우드·플랫폼 지식

## Aurora 내부 구조 (2022~23 세미나 기반 — `보관`, 재검증 필요)

- 스토리지: 3-AZ 6-way copy, Protection Group=10GB 단위, VOLUME=STRIPE SET(16 PG), PG=Full segment 3 + Tail segment 3, Quorum R/W. 세그먼트 장애 시 전체 재수신 교체.
- 동일 클러스터 Reader의 공유 Cluster Volume, redo 전달, cached-page apply 구조와 Community MySQL 복제 비교는 [[aurora-vs-mysql-replication-architecture]] 참조.
- 운영 특성: **swap 미사용 → 메모리 부족 시 RDS 대비 다운 확률 높음**. Write I/O 4KB / Read 16KB. 비용 지표는 ReadIOPS 권장. parallel query는 buffer pool 미사용(Storage Node 계산) → 비용 급증 가능. read replica + 장기 트랜잭션은 undo 전체 읽기 문제 → READ COMMITTED 검토. fast clone은 copy-on-write.
- Performance Insights(performance_schema on)는 5~10% 성능 저하. ^[2022~23 시점 수치 — 현재 동작 재검증 필요]
- BabelFish(SQL Server→Aurora PG): 당시 trigger 미지원, host_name()/datediff/format/parsename() 미지원 — **이후 개선됐을 가능성 큼, 공식 문서 재확인 필수**.
- DynamoDB: TTL, ACID 트랜잭션(글로벌 테이블 미지원 당시 기준).

## SQL Server → Azure Blob 백업 (검증 2026-07-30)

- 사전: 전용 Storage Account+Container, 범위·기간 제한 SAS, SAS 원문 저장 금지.
- `CREATE CREDENTIAL [<container-url>] WITH IDENTITY='SHARED ACCESS SIGNATURE', SECRET='<sas-token>'` → `BACKUP DATABASE ... TO URL=... WITH COPY_ONLY, CHECKSUM, STATS=5`.
- TDE DB는 인증서·개인 키 보관/복구 절차 선검증. **`SET ENCRYPTION OFF`/`DROP DATABASE ENCRYPTION KEY`는 백업의 정상 사전 단계가 아님** — 승인·인증서 백업 없이 실행 금지.
- 검증: `RESTORE VERIFYONLY`는 보조 수단, 실제 복원 테스트가 최종. SAS 만료·회수와 Credential 정리 절차 기록.

## Linux 점검 명령

- cron 로그는 배포판별 상이(`journalctl -u cron` 등). scp는 키 권한 점검 + 호스트 키 검증 우회 금지.
- 임시 비밀값: `openssl rand -base64 24` (history/채팅/문서에 남기지 않음).
- 최근 시작 프로세스: `ps -eo pid,etimes,etime,lstart,cmd --sort=etimes | awk 'NR==1 || $2<300'`.
- `ss -tulnp` 출력은 민감 인수 포함 가능 → 공유 전 마스킹.

## Docker MySQL 실습 표준

- 비밀번호는 `MYSQL_ROOT_PASSWORD_FILE=/run/secrets/...`(chmod 600), 포트는 `127.0.0.1:PORT:3306` 로컬 바인딩, `--server-id`+`--log-bin`, slow log TABLE 출력. 검증 `mysqladmin ping`.
- 복제: GTID + `SOURCE_AUTO_POSITION=1`, 복제 계정 `REQUIRE SSL` + REPLICATION SLAVE 최소 권한. `SOURCE_PASSWORD` SQL은 이력에 남음 → 시크릿 주입. XtraBackup: backup → prepare → 빈 datadir 복원 → GTID 좌표로 복제 시작. 롤백은 `STOP REPLICA` 후 `RESET REPLICA ALL`(메타데이터 삭제 — 재구성 정보 확보 후).
- 이미지 `latest` 태그 금지 — InfluxDB Docker `latest`는 2026-09-15부터 InfluxDB 3 Core를 가리킴(1.x/2.x/3.x 인증·API 전부 다름).

## 발견된 위험 자료 (원본 교정 필요)

- Docker 인덱스에 `docker rm -f $(docker ps -aq)` 무차별 파괴 명령이 필터·경고 없이 기록.
- Prometheus v2.1.0/Alertmanager v0.13.0(2018년 수준) 실습 — 0.0.0.0 바인딩 + `--web.enable-lifecycle`(무인증 원격 reload/종료) 위험.
- MySQL MMM 페이지: CentOS 7(EOL), `--privileged`, `RESET MASTER` 무경고, mmm_agent에 SUPER+`'%'` 부여 — 보관 콜아웃은 있으나 본문 위험 예제 잔존.
- Kafka 페이지는 PDF 첨부만 존재(본문 지식 없음) — 이관 필요.

## Related

- [[aurora-vs-mysql-replication-architecture|Community MySQL 복제와 Aurora Reader 아키텍처 비교]]
- [[aurora-dsql]] — 같은 Aurora 이름을 쓰지만 운영 모델이 전혀 다른 분산 변종
- [[monitoring-incident-runbook]] — 여기 정리된 Aurora 특성이 실제 장애 절차에서 쓰이는 곳
- [[sqlserver-operations]] — Azure Blob 백업 절차를 실행하는 엔진 쪽 맥락
- [[mysql-dump-load]] — 여기 정리한 Aurora 스토리지 특성이 Reader 덤프 제약·S3 직접 덤프로 나타나는 지점
