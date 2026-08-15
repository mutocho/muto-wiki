---
title: Community MySQL 복제와 Aurora Reader 아키텍처 비교
category: db운영
tags: [dba, mysql, aurora, replication, performance]
summary: Community MySQL의 독립 데이터 복제·binlog apply와 Aurora의 공유 Cluster Volume·Reader cache redo apply를 비교하고 성능, lag, 확장성, failover 차이를 정리한다.
aliases: [Aurora Reader 복제 구조, MySQL Replica와 Aurora Replica 비교]
sources: [사내 공유 (2026-08-12), "AWS: RDS MySQL read replicas / Aurora storage·replica 문서"]
status: draft
created: 2026-08-12
updated: 2026-08-15
notion_page_id: "3bdfb969-b8be-81de-9add-cd5a42ba9b05"
notion_synced: "2026-08-15T22:55:00+0900"
---

> [!tip] 핵심 Takeaway
> - **둘은 "복제"라는 같은 단어를 쓰지만 하는 일이 다르다.** Community Replica는 **독립 데이터 사본에 InnoDB 변경 경로를 전부 재수행**하고, Aurora Reader는 **공유 스토리지 위에서 cached page에 필요한 redo만 적용**한다. lag의 성질도 대응법도 여기서 갈린다
> - **Reader 증설로 쓰기 부하가 줄지 않는다** — 스토리지가 공유이므로. 읽기 확장과 쓰기 확장을 같은 수단으로 풀려는 요구가 오면 이 지점을 먼저 설명한다
> - **lag 대응이 서로 다르다**: Community는 apply 병렬도(`replica_parallel_workers`, `LOGICAL_CLOCK`)와 대량 DML 분할이 핵심, Aurora는 redo 전파·캐시 적용 지연이라 접근이 다르다 — [[monitoring-incident-runbook]]
> - 엔진 선택·아키텍처 문의에 답할 때 이 비교가 1차 근거다. Aurora 스토리지 내부 구조는 [[cloud-platform-knowledge]], MySQL 복제 운영은 [[mysql-operations]]

# Community MySQL 복제와 Aurora Reader 아키텍처 비교

Community MySQL 복제는 각 Replica가 독립된 데이터 상태를 유지하며 binlog event를 storage-engine 변경으로 적용한다. Aurora 동일 클러스터 Reader는 Writer와 Cluster Volume을 공유하고, 전달받은 redo/log record 중 자신의 buffer cache에 있는 페이지에 필요한 연산만 적용한다.

## 핵심 비교

| 구분 | Community MySQL replication | Aurora 동일 클러스터 Reader |
|---|---|---|
| 데이터 저장소 | Source와 Replica마다 별도 데이터 사본 | Writer와 Reader가 하나의 Cluster Volume 공유 |
| 변경 전달 | binlog event | redo/log stream |
| Replica 측 작업 | row 탐색, B+Tree·index 수정, 자체 undo/redo, dirty page flush | 캐시된 페이지에 redo 연산 적용; 페이지가 없으면 해당 record를 버림 |
| cache miss | 복제 적용을 위해 페이지를 읽어올 수 있음 | 복제 때문에 페이지를 읽지 않고, 실제 SELECT 때 공유 스토리지에서 최신 페이지를 읽음 |
| Reader 증가 비용 | Replica마다 독립 apply와 storage I/O | 공용 데이터 상태 + Reader별 log 수신·cache apply |
| lag의 중심 | binlog 전송, relay log, applier 및 Replica storage 처리량 | redo 전달과 Reader log applicator의 cache 적용 속도 |

## Community MySQL: 변경을 독립 데이터 사본에 적용

ROW 기반 복제도 SQL문 자체를 다시 실행하는 것은 아니지만, Replica는 row event를 자신의 InnoDB 상태에 반영해야 한다. 대상 레코드와 인덱스 페이지에 접근하고 B+Tree를 수정한 뒤 자체 undo·redo와 dirty page flush를 수행한다.

```text
Primary DML → redo + binlog → network
                            ↓
Replica relay log → applier → row/index 변경 → replica redo → page flush
```

따라서 Replica가 늘면 각 노드에 독립된 data copy, apply CPU, buffer pool 및 storage I/O 비용이 추가된다. Source의 트랜잭션 생성률이 Replica applier 처리량을 계속 초과하면 backlog와 lag가 누적된다.

## Aurora: 공유 스토리지와 Reader cache 동기화

Aurora의 Writer와 Reader는 동일한 logical Cluster Volume을 사용한다. Reader를 추가해도 Reader별 데이터 사본이나 Cluster Volume의 6개 스토리지 복제본을 새로 만드는 구조가 아니다.

```text
Writer redo ──→ Aurora Cluster Volume
       ├─────→ Reader 1 cache
       ├─────→ Reader 2 cache
       └─────→ Reader 3 cache
```

Reader는 전달된 log record의 대상 페이지가 buffer cache에 있으면 redo 연산을 적용해 캐시를 최신화한다. 페이지가 캐시에 없으면 record를 버리고, 이후 SELECT에서 필요해질 때 공유 스토리지의 최신 페이지를 읽는다. 이 때문에 복제 동기화만을 위해 사용하지 않는 페이지를 읽거나 buffer pool을 채울 필요가 없다.

Aurora redo stream은 binlog보다 페이지 변경 연산에 가까운 낮은 계층의 record다. Reader는 SQL parsing, optimizer, execution plan, PK·secondary index 탐색 같은 DML 실행 경로를 반복하지 않는다. 다만 이를 일반적인 의미의 완전한 physical replication과 동일시하기보다는 Aurora의 log-oriented storage protocol로 이해하는 편이 안전하다. ^[ambiguous]

## 성능과 확장성의 차이

대량 UPDATE가 여러 페이지와 secondary index를 바꾸면 Community MySQL의 각 Replica는 해당 변경을 자신의 InnoDB 데이터에 적용한다. Aurora에서는 공유 스토리지가 공용 데이터 상태를 유지하고 각 Reader는 캐시된 관련 페이지만 적용한다.

```text
Community: 1 Writer + N × [독립 data copy + binlog apply + redo + page write]
Aurora:    1 Shared Cluster Volume + N × [log receive + cached-page apply]
```

성능 차이의 핵심은 네트워크 사용 여부나 redo 양만이 아니라 **로그 전달 이후 각 Replica가 해야 하는 후속 작업량**이다. Reader가 많고 변경 범위가 클수록 독립적인 전체 InnoDB write pipeline을 반복하지 않는 Aurora의 이점이 커지기 쉽다. ^[inferred]

## Lag와 운영 관찰점

Community MySQL lag는 `binlog generation → network → relay log → applier throughput → replica storage` 중 한 단계가 병목이면 증가한다.

Aurora Reader lag는 `writer redo generation → redo delivery → reader log applicator → cached-page apply` 흐름의 차이다. `replica_lag_in_msec`는 Reader page cache가 Writer page cache보다 뒤처진 정도로 해석한다. Writer의 redo/storage durability 병목과 Reader의 cache apply lag는 서로 다른 문제로 나눠 봐야 한다.

Aurora Reader도 비용이 없는 것은 아니다. redo 생성률이 높고 변경 페이지가 Reader buffer pool에 많이 올라와 있으면 Reader CPU, replica lag, SELECT latency가 함께 상승할 수 있다. Writer 역시 redo를 스토리지 노드에 전송하고 write quorum acknowledgement를 받아 내구성을 확보하므로 redo·네트워크·quorum 비용을 부담한다.

운영에서는 다음을 구분한다.

- Writer redo 생성 또는 storage quorum 지연인가
- Reader로의 redo 전달이 늦는가
- Reader log applicator가 cached page 변경을 따라가지 못하는가
- Reader CPU 상승과 SELECT latency가 같은 시점에 나타나는가

관련 모니터링 원칙은 [[monitoring-incident-runbook]]을 함께 본다.

## Failover와 적용 범위

Community 비동기 Replica 승격은 GTID·relay log와 미적용 트랜잭션 상태를 확인해야 한다. Aurora Reader는 Writer와 durable Cluster Volume을 공유하므로 별도 storage dataset을 catch-up한 뒤 승격하는 구조가 아니다. 이 compute/storage 분리는 Reader를 standby compute처럼 활용하게 한다.

반대로 Community MySQL의 독립 Replica는 별도 데이터 사본, 다른 버전·구성, replication filtering, delayed replication, 다른 리전·클라우드·온프레미스 DR, CDC downstream에 더 적합할 수 있다. Aurora 동일 클러스터 Reader는 이러한 독립 복제 목적과 다르며, 필요하면 Global Database나 클러스터 간 binlog replication을 별도로 선택해야 한다.

## 판단 문장

> Community MySQL은 변경 정보를 보내 Replica가 독립 DB 상태에 InnoDB 변경을 적용하고, Aurora는 공유 스토리지를 기반으로 Reader가 자신의 캐시에 필요한 redo 연산만 적용한다.

## Related

- [[mysql-operations|MySQL/Aurora MySQL 운영 지식]]
- [[cloud-platform-knowledge|클라우드·플랫폼 지식]]
- [[monitoring-incident-runbook|모니터링·장애 대응 런북]]
- [[mysql-dump-load]] — 공유 스토리지 구조 때문에 Reader 덤프가 락 제약을 받는다는 추정의 근거 페이지

## Sources

- [AWS — Read replicas for Amazon RDS for MySQL](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_MySQL.Replication.ReadReplicas.html)
- [AWS — Aurora storage reliability](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.Overview.StorageReliability.html)
- [AWS Prescriptive Guidance — Aurora Replicas](https://docs.aws.amazon.com/prescriptive-guidance/latest/aurora-replication-options/aurora-replicas.html)
- [AWS — Aurora Replica status](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora_replica_status.html)
- [AWS — Aurora high availability](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Concepts.AuroraHighAvailability.html)
- [AWS — Aurora MySQL replication with MySQL](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/AuroraMySQL.Replication.MySQL.html)
