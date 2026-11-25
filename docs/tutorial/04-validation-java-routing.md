# 第 4 章 校验、Java 路由和交接给审核队列（REST 契约 + SQS）

> 本章讲解视频：[../videos/p4-route.mp4](../videos/p4-route.mp4)

## 这一章解决什么问题？

worker 拿到了记录，但它还什么都没做。真正的工作是三步：

1. **校验**（validation）：文件是不是我们收到的那份，字段能不能用。
2. **路由**（routing）：这份文档该进哪个审核队列，多急。
3. **交接**（human handoff）：把它放进审核员的队列，并且留下审计记录。

路由和审核队列放在 Java 服务里（Spring Boot 3，`routing-svc/`，端口 8891）。Python 和 Java 之间只有两种连接：一个同步的 REST 调用，一个异步的 SQS 消息。两种都有契约文件。

## 校验查什么？

`rmflow/validation.py`（锚点 `validate`）。它不抛异常，而是把每一项检查的结果都列出来：

- `file_type`：Lambda 看到的头几个字节是 pdf 或 csv。
- `file_size`：一字节到五 MB。
- `integrity`：Lambda 在 S3 上算出的 sha256，和收件时算的一致。不一致说明文件在中间被换过。
- `required_fields`：按文档类型要求的字段，比如发票要 amount 和 vendor。
- `amount_format`：金额能解析成数字。

同时给出一个风险分（risk score）：金额超过一万加六十分，缺字段加三十分。校验没过也不丢掉，照样路由，只是进 `corrections` 队列让人看。

## 为什么路由要单独成一个服务，又为什么是同步调用？

路由规则会经常改（第 7 章就要灰度发布一个新版本），而且要给审核那一侧共用，所以放在 Java。
worker 需要路由的结果才能决定往哪交接，所以是同步 REST：`POST /v1/routing/decisions`（`RoutingController`，锚点 `routing-endpoint`）。
同一个 `(record_id, seq)` 永远得到同一个 `decision_id`，所以 worker 重试拿到的是同一个答案，不会多出一条决定。

## Java 挂了、慢了怎么办？（bounded retries + fallback）

`rmflow/routing_client.py`（锚点 `routing-retry`）：

- 最多四次。间隔 0.2 秒、0.4 秒、0.8 秒，封顶 1.6 秒，再加上下百分之二十的抖动（jitter），免得所有 worker 同时重试。
- 只有 5xx 和超时才重试。4xx 是请求本身错了，重试也没用。
- 四次都失败，走 fallback：进 `manual-triage` 队列，原因里写清楚是哪几次失败。**记录不会卡在半路，最差也会到一个人手里。**

`tests/test_step04_validate_route.py::test_retries_are_bounded_and_end_in_the_fallback_route` 用 httpx 的 MockTransport 一直超时，断言正好四次调用、总等待不超过 1.68 秒、最后走 fallback。

## 交接为什么走 SQS，不直接调 Java？

审核队列那边短暂不可用时，worker 不应该停下。消息放进 `rm-handoff` 就算交出去了。
Java 的 `HandoffConsumer` 长轮询这个队列。收进来时做两层去重（`ReviewService.takeHandoff`，锚点 `handoff-intake`）：

- `handoff_inbox` 表的主键是 `(record_id, seq)`。SQS 重复投递，第二次插入失败，直接确认掉。
- 任务表按 record_id 唯一。`ON CONFLICT ... DO UPDATE ... WHERE review_tasks.seq < EXCLUDED.seq`（锚点 `task-upsert`）：新版本覆盖旧任务，迟到的旧版本什么也改不了，审计里记一条 `HANDOFF_STALE`。

## 契约怎么写，两边怎么测？

`contracts/` 里每个文件是一份快照：

| 文件 | 谁产出 | 谁依赖 |
|---|---|---|
| `routing-decision.v1.json` | Python 发请求，Java 回响应 | 两边 |
| `handoff.v1.json` | Python worker | Java consumer |
| `decision.v1.json` | Java outbox | Python exporter（第 5 章） |

Python 测「我发出去的形状和快照完全一样」；Java 测「我回的响应保留了快照里每个字段、类型不变」（`ContractTest`，锚点 `java-contract-test`）。多加字段可以，改名、删除、改类型都会红。

## 跑一次看看

```bash
./scripts/submit_sample.sh "Invoice 5520"
curl -s localhost:8890/v1/records/<record_id>/timeline
```

真实输出（两边的事件按时间合在一起，锚点 `timeline-merge`）：

```text
19:37:28.479 intake SUBMITTED     client:acme-portal
19:37:28.711 intake LAMBDA_SEEN   lambda:326dda25-...
19:37:28.776 intake SQS_RECEIVED  dispatcher
19:37:28.779 intake PARTITIONED   dispatcher
19:37:28.809 intake WORKER_PICKED worker:w1
19:37:28.818 intake VALIDATED     worker:w1
19:37:28.964 audit  ROUTED        routing:v1
19:37:28.977 intake ROUTED        worker:w1
19:37:28.997 intake HANDED_OFF    worker:w1
19:37:29.016 audit  TASK_CREATED  worker:w1
```

从提交到审核队列里出现任务，这一次是五百三十七毫秒（单次，本机，只说明链路是通的，不是性能结论）。

## 怎么 checkout 到这一步跑起来

```bash
git checkout step-04
./scripts/demo.sh                    # 多了 Java 服务（首次会 mvn package）
.venv/bin/python -m pytest           # 30 passed
(cd routing-svc && JAVA_HOME=/opt/homebrew/opt/openjdk@21 mvn -q test)   # 8 个 Java 测试
```
