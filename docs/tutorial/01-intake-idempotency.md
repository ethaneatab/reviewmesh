# 第 1 章 先让一条记录只进来一次（intake + idempotency key）

> 本章讲解视频：[../videos/p1-intake.mp4](../videos/p1-intake.mp4)

## 这一章解决什么问题？

审核流程的第一步是「收件」：客户端把一份文档和几个字段交上来。
网络会超时，客户端会重试。重试一次，后端就可能多建一条记录，后面审核员就会审两遍。
所以第一件事不是功能多，而是：**同一个请求重试多少次，都只算一次。**

## 最小版本长什么样？

- 一个 FastAPI 服务（`rmflow/api.py`），端口 8890。
- 一个 Postgres（`docker-compose.yml`，宿主机端口 54390）。
- 三张表：`records`、`record_versions`、`idempotency_keys`，外加一张只追加的时间线 `record_events`（`rmflow/migrations/001_intake.sql`）。

## 幂等键放在哪一层？

假设：只在内存里记一下「这个 key 见过」就够了。
不够。两个副本各有各的内存；进程一重启也全丢。
所以 key 要落库，而且要靠**主键冲突**来挡，不能靠「先查再插」。先查再插有竞态：两个请求同时查，都说没有，然后都插进去。

做法在 `rmflow/intake.py` 的 `_claim_key`（锚点 `idempotency-guard`）：

1. 在同一个事务里先 `INSERT ... ON CONFLICT DO NOTHING` 插入 `(client_id, key)`。
2. 插进去了，说明这个 key 归我，接着建记录、写时间线、把响应存回这一行，然后一起提交。
3. 没插进去，说明别人先到了。`SELECT ... FOR UPDATE` 会一直等到对方提交，然后把对方存的响应原样返回，带上头 `Idempotent-Replay: true`。
4. 同一个 key 但请求体不一样，返回 422。这是客户端的 bug，要大声报出来。

还有一个小细节：record id 不是随机数，而是 `sha256(client_id, key)` 的前 16 位。这样就算真的有请求绕过了保护，它也会撞到同一个主键上。

## 跑一次看看

起服务：

```bash
./scripts/demo.sh          # 这一步只有 Postgres + intake API
```

同一个 key 发两次（真实输出）：

```text
HTTP/1.1 201 Created
{"record_id":"rec_5c8e1b4e508074b0","seq":1,"status":"RECEIVED","trace_id":"584bfe34a5b94f60b57ce391fb6d7934"}
HTTP/1.1 200 OK
idempotent-replay: true
{"seq":1,"status":"RECEIVED","trace_id":"584bfe34a5b94f60b57ce391fb6d7934","record_id":"rec_5c8e1b4e508074b0"}
```

服务端的结构化日志（每行一个 JSON，带 record_id 和 stage）：

```text
{"ts": "2026-11-25T19:20:43.205Z", "level": "info", "logger": "intake", "msg": "record submitted", "record_id": "rec_5c8e1b4e508074b0", "stage": "SUBMITTED"}
{"ts": "2026-11-25T19:20:43.225Z", "level": "info", "logger": "intake", "msg": "idempotent replay", "record_id": "rec_5c8e1b4e508074b0", "stage": "SUBMITTED"}
```

## 怎么证明保护是活的？

`tests/test_step01_idempotency.py::test_concurrent_retries_create_exactly_one_record` 用八个线程同时发同一个请求，断言数据库里只有一条记录。

把保护关掉再跑（`RM_LAB_SABOTAGE=no_idempotency`），它必须红：

```bash
RM_LAB_SABOTAGE=no_idempotency .venv/bin/python -m pytest tests/test_step01_idempotency.py -k concurrent
# FAILED tests/test_step01_idempotency.py::test_concurrent_retries_create_exactly_one_record
```

全部打开时 5 个测试都过。

## 修订版本（revision）为什么也要幂等？

一条记录可以被客户端改了再交，变成第 2 版、第 3 版。版本号 `seq` 用 `UPDATE ... SET latest_seq = latest_seq + 1 RETURNING` 在行锁下分配。
修订请求也带幂等键：重试不会让 seq 跳两格。后面第 3 章的「同一条记录的步骤按顺序执行」就是按这个 seq 排的。

## 怎么 checkout 到这一步跑起来

```bash
git checkout step-01
./scripts/demo.sh
.venv/bin/python -m pytest      # 5 passed
./scripts/stop.sh
```
