# 第 8 章 看得见：结构化日志、指标、告警、索引实测，和教学页面

> 本章讲解视频：[../videos/p8-observe.mp4](../videos/p8-observe.mp4)

## 这一章解决什么问题？

前七章把功能做全了。可是线上出事时，第一个问题永远是「这条记录现在在哪、卡在哪一步」。
这一章回答三件事：**一条记录的每一次交接能不能追到；系统整体健不健康；慢查询是不是走了设计好的索引。** 最后把这些都接到一个教学页面上，让人从界面上看到真实的状态一步步亮起来。

## 一条记录怎么追？

- 每条记录在收件时生成一个 `trace_id`，跟着 S3 元数据、Lambda、SQS 消息、worker、Java 请求头 `X-Trace-Id`、审计详情一路走。
- Python 每行日志是一个 JSON（`rmflow/logs.py`），固定字段 `record_id`、`seq`、`stage`、`worker`、`trace_id`。Java 用 logstash encoder，同样把 `record_id` 和 `trace_id` 放进 MDC。真实的两行：

```text
{"ts": "2026-11-26T01:34:22.704Z", "level": "info", "logger": "worker", "msg": "worker up", "worker": "w1", "data": {"port": 8892, "standby": false}}
{"ts":"2026-11-25T17:35:02.532357-08:00","message":"routed rec_d2d0b238d225098f seq 1 -> claims via v1","level":"INFO","record_id":"rec_d2d0b238d225098f","trace_id":"2ef71b24c7024d69ae5bcf03ac1bac74",...}
```

- 时间线接口（第 4 章）把两边的事件按时间合在一起，这是「handoff 状态可追踪」最直接的形式。

## 系统健不健康？

`rmflow/ops.py`（锚点 `ops-alerts`）算四种告警：死信队列不为空、记录卡在 STORED 超过二十秒、worker 心跳断了、灰度被自动回滚。
同样的条件写成了 Prometheus 规则（`ops/prometheus/alerts.yml`），`promtool` 校验通过：

```text
Checking /etc/prometheus/alerts.yml
  SUCCESS: 4 rules found
```

指标从 `/metrics`（intake 8890、worker 8892 到 8895）和 Java 的 `/actuator/prometheus` 拉。Prometheus 和 Grafana 放在 compose 的 `obs` profile 里，默认不起，因为本机的 colima 是好几个项目共用的。要看 dashboard：

```bash
docker-compose -p reviewmesh --profile obs up -d prometheus grafana   # 8896 / 8897
```

不想起 Prometheus 也行，前端 `/ops` 页直接显示同样的告警、队列深度和记录状态。

## 索引是按查询路径设计的吗？

每个索引都对应一条具体的查询。`scripts/explain_paths.py` 往测试库里灌两万条记录、十万条事件，`ANALYZE` 之后跑 `EXPLAIN ANALYZE`：

| 查询 | 用到的索引 |
|---|---|
| reconciler：还在 STORED 的记录，最老的先 | `records_stuck_stored`（部分索引） |
| 时间线：一条记录的所有事件 | `record_events_by_record` |
| 审核队列：一个队列里 OPEN 的、最急的先 | `review_tasks_queue_path` |
| 审计：一条记录的全部审计 | `audit_events_by_record` |

`tests/test_step08_query_paths.py`（锚点 `test-explain`）断言计划里有那个索引、而且没有 `Seq Scan`。完整的计划在 `docs/results/explain.md`。

## 教学页面怎么做到「真实」？

`/learn` 页点「提交样例」以后，后端（`rmflow/learn.py`）真的提交一张发票，并且用同一个幂等键再发一次。页面每 0.8 秒问一次 `/learn/api/runs/<id>`，后端逐项去查：

- Postgres 里有没有 `SUBMITTED`、`LAMBDA_SEEN`、`PARTITIONED`、`VALIDATED`、`ROUTED`、`EXPORTED` 这些事件；
- S3 里有没有那个对象；
- Java 的审计里有没有 `CLAIMED`、`APPROVED`。

有了才亮，没有就灰着。认领和通过两步要人点按钮。每一步旁边有「看源码」，链接由 `scripts/learn_anchors.py` 扫出来的 `@learn` 锚点生成，格式是 `仓库/blob/<构建时的 commit>/<文件>#L起-L止`，行号不手写；`scripts/check_anchors.py` 检查引用的锚点都存在、标记行确实在那、生成文件没有过期。

另外三个支线标签页：扩容（环上搬了哪些 key）、灰度与回滚、表结构迁移（当前 phase、列、Flyway 历史）。还有「面试题」和「日常问题」两个标签页，渲染 `docs/interview.md` 和 `docs/problems.md`。

`e2e/learn.spec.ts` 从界面点一遍：十个阶段依次亮起、`kv-submit` 里能看到「HTTP 200，replay=true」、分区那一步的 JSON 里有 `vnode`、导出那一步的 JSON 里有 S3 key 和 `APPROVED`；每个源码链接的格式对、指向的行在本地文件里确实存在。

## 怎么 checkout 到这一步跑起来

```bash
git checkout step-08
./scripts/demo.sh
open http://127.0.0.1:5189/learn
.venv/bin/python scripts/check_anchors.py
npx playwright test               # 10 passed
```
