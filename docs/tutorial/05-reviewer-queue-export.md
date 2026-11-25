# 第 5 章 审核员的界面、登录和导出（JWT + React + S3 导出）

> 本章讲解视频：[../videos/p5-review.mp4](../videos/p5-review.mp4)

## 这一章解决什么问题？

到第 4 章为止，任务已经进了 Java 的审核队列，但只能用 curl 看。这一章补上「人」的那一段：

- 审核员登录，看到自己的队列，认领、通过、驳回、转人工。
- 每条记录有一条完整的时间线，Python 和 Java 两边的状态都在上面。
- 审核结论落到 S3，变成下游能读的 CSV 和 Parquet。

## 登录谁来管？

Java 服务发 token（`/v1/auth/login`，`AuthController`），HS256，issuer 是 `reviewmesh`。Python 用同一个密钥验（`rmflow/auth.py`）。
密钥只从环境变量 `RM_JWT_SECRET` 读，默认值是一个写明了「只能本地用」的占位串。
角色有五种：`submitter`（客户端提交）、`reviewer`、`senior`、`ops`、`service`（worker 调路由用）。每个接口自己声明要哪几种。

## 两个审核员同时点「认领」会怎样？

假设：先查状态是 OPEN，再改成 CLAIMED。两个人同时查，都是 OPEN，都改成功了。
所以认领只有一条 SQL：`UPDATE ... SET status='CLAIMED', reviewer=? WHERE id=? AND status=?`（`ReviewService.claim`，锚点 `claim`）。影响行数是一才算赢，零就回 409。
`ReviewFlowTest.twoReviewersRaceForOneTaskAndExactlyOneWins` 用两个线程同时认领，断言正好赢一个。e2e 里也有一条：rita 认领以后，sam 在页面上看不到「通过」按钮。

## 结论怎么到 S3？为什么要 outbox？

审核员点「通过」以后要做两件事：改数据库，通知下游。
假设：先提交数据库，再发 SQS。进程在两步中间崩了，数据库说已通过，下游永远不知道。
所以用 transactional outbox（`DecisionOutbox`，锚点 `decision-outbox`）：结论和要发的消息在**同一个事务**里写进 `decision_outbox` 表，一个每半秒跑一次的 poller 把没发的发出去，再标记已发。最坏情况是发两次，而下游按 `(record_id, seq)` 写同一个 S3 key，发两次也只有一个文件。

Python 的 exporter（`rmflow/exporter.py`，锚点 `export-decision`）收到 `decision.v1`，写一行 CSV：

```text
exports/decisions/dt=2026-11-25/rec_7cc86543109548d1-s1.csv
record_id,seq,title,doc_type,queue,outcome,reviewer,reason,decided_at,trace_id
rec_7cc86543109548d1,1,E2E invoice 1795635841139,invoice,finance,APPROVED,rita,totals match the purchase order,...
```

`POST /v1/exports`（ops 角色）把所有结论一次导成 `exports/batch/<时间>.parquet` 和同内容的 CSV。`tests/test_step05_export_cache.py` 用 pyarrow 把 Parquet 读回来核对。

## Redis 在这里做什么？

客户端提交完会不停地问「我的件到哪了」。这个查询打到 `GET /v1/records/{id}/status`（`rmflow/cache.py`，锚点 `status-cache`），先查 Redis，没有再查 Postgres 并缓存一秒。代价是状态最多晚一秒。真实输出：

```text
{"record_id":"rec_7cc86543109548d1","status":"APPROVED","seq":1,...,"cache":"miss"}
{"record_id":"rec_7cc86543109548d1","status":"APPROVED","seq":1,...,"cache":"hit"}
```

Redis 的另一个用途是第 3 章的分布式锁。

## 前端有哪些页？

React + Vite + TypeScript（`frontend/`，端口 5189）。Vite 把 `/api/intake` 代理到 8890，`/api/review` 代理到 8891。

- `/queue`：按队列分标签页，按状态筛选，每两秒刷新。
- `/records/<id>`：时间线。蓝点是 Python 的事件，橙点是 Java 的审计，点「详情」看那一步的原始 JSON。
- `/ring`：哈希环。外圈刻度是虚拟节点，点是真实的 record id，颜色是它的主人。点「扩容」以后换了主人的点会往里缩一圈、变大。

## 怎么证明？

`e2e/queue.spec.ts` 从界面点一遍：提交一张发票 → 在 finance 队列里出现 → rita 认领 → 通过 → 打开时间线，`EXPORTED` 那一步的 JSON 里有 S3 key 和 `APPROVED`。

```text
  ✓  1 e2e/queue.spec.ts › a submitted invoice reaches the finance queue, gets approved and exported (6.2s)
  ✓  2 e2e/queue.spec.ts › two reviewers: only the one who claimed can decide (670ms)
  ✓  3 e2e/queue.spec.ts › ring page scales out and shows only keys moving to w4 (388ms)
```

## 怎么 checkout 到这一步跑起来

```bash
git checkout step-05
./scripts/demo.sh            # 多了前端 http://127.0.0.1:5189
npm install && npx playwright test
```
