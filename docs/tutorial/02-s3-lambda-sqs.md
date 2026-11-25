# 第 2 章 文档进 S3，Lambda 把它送进队列（S3 → Lambda → SQS）

> 本章讲解视频：[../videos/p2-s3-lambda.mp4](../videos/p2-s3-lambda.mp4)

## 这一章解决什么问题？

第 1 章只收了字段。真实的审核件是 PDF 或表格，几百 KB 到几 MB，不适合塞进数据库。
而且收件和后面的处理不应该绑在一个请求里：后面慢了、挂了，收件接口也不能跟着慢。
所以这一章把两段拆开：**收件只负责把文件放进 S3；S3 的事件触发一个 Lambda，由它把这条记录放进 SQS。** 中间任何一段失败，都有一个兜底。

## 文件什么时候写进 S3？

假设：先提交数据库，再上传 S3。
问题是上传失败时，记录已经提交了，文件却没了，而且我们手上也没有文件可以重传。
所以反过来：上传放在**同一个数据库事务里、提交之前的最后一步**（`rmflow/storage.py`，锚点 `s3-store`）。
上传失败，事务回滚，幂等键也一起回滚，客户端重试会从头再来。S3 的 key 是 `inbox/<record_id>/v<seq>/<文件名>`，record id 由幂等键算出来，所以重传覆盖的还是同一个对象。

## Lambda 做什么？

`lambdas/s3_intake/handler.py`（锚点 `lambda-handler`）只做三件小事：

1. 读对象，算 sha256、大小，看头几个字节猜类型（pdf / csv）。
2. 往记录时间线写一条 `LAMBDA_SEEN`，actor 是 Lambda 的 request id。
3. 发一条 `intake.v1` 消息到 SQS 队列 `rm-intake`。

pipeline 进程（`rmflow/pipeline.py`）消费这个队列。这一章它只记一条 `SQS_RECEIVED`，第 3 章它会按一致性哈希把消息转给某个 worker。

## 真跑出来的第一个坑：Lambda 根本没起来

第一次部署后，提交了一份 PDF，时间线只有 `SUBMITTED`，Lambda 那一步一直不出现。LocalStack 日志里是这一行：

```text
WARN --- l.s.l.i.executor_endpoint : Execution environment startup failed: {"errorMessage": "Unable to import module 'handler': No package metadata was found for scramp", "errorType": "Runtime.ImportModuleError"}
```

- 假设一：数据库连不上。不对，错误发生在 import 阶段，还没走到连接。
- 假设二：zip 里少了 scramp。看 zip 内容，`scramp/` 目录在。
- 再看报错原文：少的是 **package metadata**。scramp 在 import 时用 `importlib.metadata` 读自己的版本号，需要 `scramp-*.dist-info/`。
- 修法：打包时按「发行包」而不是按「模块目录」拷，把 dist-info 一起放进 zip（`rmflow/bootstrap.py` 的 `lambda_zip`）。

修好之后同样的提交，时间线三步齐了（真实输出，截断）：

```text
5 SUBMITTED   client:acme-portal  {"s3_key": "inbox/rec_d4996c018b6d589c/v1/invoice.pdf", "status": "STORED", ...}
6 LAMBDA_SEEN lambda:be99449d-...  {"via": "s3-lambda", "sniff": "pdf", "size": 24, "sha256": "124ae51c...", ...}
7 SQS_RECEIVED dispatcher         {"queue": "rm-intake", "message": {...}, "receive_count": 1}
```

## Lambda 丢了事件怎么办？（fallback path）

上面那次失败其实没有丢记录。`reconcile_once`（锚点 `reconciler`）每五秒扫一次：状态还是 `STORED`、而且超过二十秒没动的记录，直接发一条 `via: reconciler` 的消息进队列。
那次的真实时间线：

```text
2 SUBMITTED    client:acme-portal  19:23:47.338
3 RECONCILED   reconciler          19:24:08.388
4 SQS_RECEIVED dispatcher          19:24:08.393
```

这个查询走一个**部分索引** `records_stuck_stored ON records(updated_at) WHERE status='STORED'`（`rmflow/migrations/002_reconcile_index.sql`）。正常情况下这张索引几乎是空的，扫起来很便宜。
重复怎么办？Lambda 晚到加上 reconciler 补发，同一个 seq 可能进队两次。第 3 章的 worker 按 seq 去重，所以多一次也没事。

## 一直失败的消息去哪里？（bounded retries + DLQ）

`rmflow/sqsloop.py` 的处理规则：

- 处理失败不删消息，把可见性超时推到 2 的 n 减 1 次方秒（n 是第几次收到），封顶十六秒。
- 每个队列都配了 `RedrivePolicy`，收到第四次还失败，SQS 自己把它移进对应的 `-dlq`。

`tests/test_step02_s3_lambda_sqs.py::test_poison_message_is_parked_in_the_dlq_after_bounded_retries` 发一条格式不对的消息，断言它最后出现在 DLQ 里。

## 怎么 checkout 到这一步跑起来

```bash
git checkout step-02
./scripts/demo.sh                     # Postgres + Redis + LocalStack，bootstrap，API，pipeline
./scripts/submit_sample.sh            # 提交一份样例 PDF
.venv/bin/python -m pytest            # 10 passed（其中一条 live 测试要 demo.sh 在跑）
./scripts/stop.sh && docker-compose -p reviewmesh stop
```
