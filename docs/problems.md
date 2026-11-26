# 日常问题与解决

十个问题。q01–q06 是做这个仓库时**真实踩到**的（报错原文照贴）；q07–q10 是这类系统在生产上的**典型事故**，用仓库里的「能失败的对照」复现出来（把保护关掉，测试变红的输出也是真实的）。
每题在学习页「日常问题」标签页里都有一段逐行高亮的讲解视频位，源数据在 `video/problems.src.json`。

## q01-lambda-dist-info Lambda 一直起不来（真实）

### 现象

提交一份 PDF，时间线只有 `SUBMITTED`，`LAMBDA_SEEN` 一直不出现。LocalStack 日志：

```text
WARN --- l.s.l.i.executor_endpoint : Execution environment startup failed: {"errorMessage": "Unable to import module 'handler': No package metadata was found for scramp", "errorType": "Runtime.ImportModuleError"}
```

### 在哪里

[rmflow/bootstrap.py](../rmflow/bootstrap.py)，锚点 `lambda-zip-dist`；修复前的代码在 [docs/problems/snippets/lambda_zip_before.py](problems/snippets/lambda_zip_before.py)（锚点 `before-lambda-zip`）。

### 怎么定位

- 假设一：Lambda 连不上 Postgres。排除：错误发生在 import 阶段，还没走到连接。
- 假设二：zip 里没有 scramp。排除：`scramp/` 目录在 zip 里。
- 读报错原文：缺的是 package metadata。scramp 在 import 时用 `importlib.metadata` 读自己的版本，需要 `scramp-*.dist-info/`。

### 怎么解决

修复前按模块目录拷 `.py`：

```python
for f in sorted(origin.parent.rglob("*.py")):
    put(f, f"{mod}/{f.relative_to(origin.parent)}")
```

修复后按发行包拷，带上 dist-info：

```python
dist = importlib.metadata.distribution(dist_name)
for f in sorted(dist.files or [], key=str):
    put(Path(str(dist.locate_file(f))), str(f))
```

### 怎么证明修好了

同样的提交，时间线变成 `SUBMITTED → LAMBDA_SEEN → SQS_RECEIVED`。修复前那条记录没丢：reconciler 二十秒后补发了（`RECONCILED` 事件），这也顺带证明了 fallback 路径是活的。`tests/test_step02_s3_lambda_sqs.py::test_live_s3_event_runs_the_lambda_and_reaches_sqs` 现在是绿的。

### 面试怎么讲

S：S3 触发的 Lambda 起不来，记录卡在 STORED。T：找出原因，并确认没丢数据。A：读完报错原文，发现缺的是包元数据不是模块，改成按发行包打包。R：链路恢复，而期间的记录被 reconciler 补上，一条没丢。

## q02-backfill-erases-claims 回填差点抹掉新版本的认领（真实）

### 现象

```text
MigrationCompatTest.everyStepRunsOldAndNewSideBySide
expected: 0L
 but was: 1L
```

只写新列的版本（NEW_ONLY）认领了一条任务以后，「待回填行数」从 0 变成 1。

### 在哪里

[MigrationService.java](../routing-svc/src/main/java/dev/reviewmesh/migration/MigrationService.java)，锚点 `backfill`；修复前在 [snippets/backfill_before.java](problems/snippets/backfill_before.java)（锚点 `before-backfill`）。

### 怎么定位

- 假设：回填漏了一行。把那一行打出来：`reviewer_id` 有值，`reviewer` 为空，是 NEW_ONLY 刚认领的。
- 这不是漏，是 NEW_ONLY 的正常写法。判断条件把正常数据当成了脏数据。
- 顺着看到更大的坑：清理语句「文本空、id 不空就清 id」如果在 NEW_ONLY 上线后跑，会抹掉所有新认领。

### 怎么解决

修复前：

```java
" WHERE (t.reviewer IS NULL) <> (t.reviewer_id IS NULL) OR ..."
int cleared = db.update("UPDATE review_tasks SET reviewer_id = NULL WHERE reviewer IS NULL AND reviewer_id IS NOT NULL");
```

修复后：只看「文本有值但 id 没有或对不上」；清理只允许在 DUAL_WRITE 版本里跑。

```java
" WHERE t.reviewer IS NOT NULL AND (t.reviewer_id IS NULL OR r.handle <> t.reviewer)"
int cleared = phase.phase() == ReviewerPhase.DUAL_WRITE ? db.update(...) : 0;
```

### 怎么证明修好了

`MigrationCompatTest`（锚点 `test-expand-contract`）三个测试全绿；修复前第一个是红的（上面的输出）。V3 的删列守卫用同一个条件。

### 面试怎么讲

S：做 reviewer 文本列到外键的 expand/contract 迁移。T：保证每一步新旧版本并行都不出错。A：测试让相邻两个版本共用一张表，抓到回填条件把新版本的正常数据当脏数据，还发现清理语句会抹掉新认领，于是收紧条件并限制运行阶段。R：五步迁移在测试和演示库上都走通，删列后老客户端读到的审核员名字仍然正确。

## q03-contract-before-backfill 删列跑早了（真实）

### 现象

演示库上重启 Java 服务时用了默认配置，Flyway 一路迁到 V3，而回填还没跑：

```text
Migrating schema "review" to version "3 - contract drop reviewer text"
ERROR: contract blocked: 2 review_tasks rows are not backfilled (POST /v1/migration/backfill)
Migration of schema "review" to version "3 - contract drop reviewer text" failed! Changes successfully rolled back.
```

### 在哪里

[V3__contract_drop_reviewer_text.sql](../routing-svc/src/main/resources/db/migration/V3__contract_drop_reviewer_text.sql)，锚点 `contract-guard`；没有守卫的版本在 [snippets/contract_before.sql](problems/snippets/contract_before.sql)（锚点 `before-contract`）。

### 怎么定位

- 服务没起来，先看 Flyway 日志：是 V3 失败，原因是守卫抛的异常，事务已回滚。
- 查表：`reviewer` 列还在，两行只有文本没有 id，正是还没回填的两行。

### 怎么解决

没有守卫时只有一句 `ALTER TABLE review_tasks DROP COLUMN reviewer;`，会静默成功并丢数据。现在删列前先数待回填的行，不为零就 `RAISE EXCEPTION`。然后按顺序重来：`RM_FLYWAY_TARGET=2 RM_MIGRATION_PHASE=DUAL_WRITE` 启动 → 回填到 `remaining: 0` → `RM_MIGRATION_PHASE=NEW_ONLY` 启动，V3 才通过。

### 怎么证明修好了

`MigrationCompatTest.contractRefusesToRunBeforeTheBackfill` 断言 V3 报出 `contract blocked: 1 review_tasks rows are not backfilled`，而且数据没丢。

### 面试怎么讲

S：滚动迁移的最后一步是删旧列，不可逆。T：防止有人提前执行。A：在迁移里加一段守卫，条件不满足就抛异常让整个迁移回滚。R：演示库上真的被拦下过一次，按正确顺序重来后数据完整。

## q04-stale-jar-constructor 找不到默认构造函数（真实）

### 现象

```text
Caused by: org.springframework.beans.BeanInstantiationException: Failed to instantiate [dev.reviewmesh.review.TaskRepository]: No default constructor found
Caused by: java.lang.NoSuchMethodException: dev.reviewmesh.review.TaskRepository.<init>()
```

### 在哪里

[TaskRepository.java](../routing-svc/src/main/java/dev/reviewmesh/review/TaskRepository.java)，锚点 `repo-constructors`；修复前在 [snippets/repo_before.java](problems/snippets/repo_before.java)（锚点 `before-repo-constructors`）。

### 怎么定位

- 看最底下的 Caused by：Spring 在找无参构造函数。
- 为迁移测试加了第二个公开构造函数。有多个构造函数时，Spring 不再自动选，退回无参构造。
- 修了以后又出现一次同样的错：重启脚本用的是没重新打包的旧 jar。

### 怎么解决

给生产用的构造函数加 `@Autowired`，测试用的那个保留。重启前先 `mvn -q -DskipTests package`（`scripts/demo.sh` 会比较源码和 jar 的时间，过期就重新打包）。

### 怎么证明修好了

`mvn test` 里依赖 Spring 上下文的 `ContractTest`、`ReviewFlowTest` 全部通过；服务能正常启动并通过健康检查。

### 面试怎么讲

S：为测试加了一个构造函数，服务就起不来。T：定位到底是哪一层的问题。A：看错误栈最底下的原因，明确标注注入用的构造函数；第二次复现时先确认运行的是新包。R：服务恢复，之后重启脚本会自动检查 jar 是否过期。

## q05-search-path 表建好了，SQL 却报语法错误（真实）

### 现象

```text
org.springframework.jdbc.BadSqlGrammarException: PreparedStatementCallback; bad SQL grammar [INSERT INTO users(username, password_hash, role, display_name) VALUES (?,?,?,?) ON CONFLICT DO NOTHING]
```

### 在哪里

[application.yml](../routing-svc/src/main/resources/application.yml)，锚点 `datasource-url`；修复前在 [snippets/datasource_before.yml](problems/snippets/datasource_before.yml)（锚点 `before-datasource-url`）。

### 怎么定位

- 假设一：SQL 写错。把语句放到 psql 里执行，原始错误是 relation "users" does not exist。
- `\dn` 一看，Flyway 按 `spring.flyway.schemas: review` 把表建在 `review` 模式里；应用连接没有指定模式，查的是 `public`。

### 怎么解决

```yaml
url: ${RM_JDBC_URL:jdbc:postgresql://127.0.0.1:54390/reviewmesh}                       # 修复前
url: ${RM_JDBC_URL:jdbc:postgresql://127.0.0.1:54390/reviewmesh?currentSchema=review}  # 修复后
```

### 怎么证明修好了

服务启动后 `POST /v1/auth/login` 返回 token；之后所有 Java 测试也都用带模式的连接串。

### 面试怎么讲

S：服务第一次启动就失败，报的是语法错误。T：找出真正原因。A：绕过驱动的包装，直接看数据库原始报错，发现是模式不一致。R：连接串上指定模式，应用和迁移工具看同一个地方。

## q06-stop-race 重启后请求打到了正在退出的旧进程（真实）

### 现象

重启 API 后，健康检查通过，紧接着提交请求失败，curl 退出码 7（连接被拒绝）。新进程的日志文件里混着旧进程的退出信息：

```text
INFO:     Shutting down
INFO:     Finished server process [39142]
```

### 在哪里

[scripts/stop.sh](../scripts/stop.sh)，锚点 `stop-by-pid`；修复前在 [snippets/stop_before.sh](problems/snippets/stop_before.sh)（锚点 `before-stop-by-pid`）。

### 怎么定位

- 健康检查成功，说明有进程在 8890 上应答；随后连接被拒绝，说明那个进程消失了。
- 日志里旧进程的 pid 在新日志里出现：健康检查打到的是还在优雅退出的旧进程。

### 怎么解决

修复前发完信号立刻删 pid 文件；修复后发信号后轮询 `kill -0`，最多等十秒，还在才 `kill -9`。始终只按 `.runtime/*.pid` 里记的 pid 停，从不按进程名杀（同一台机器上还有别的项目在跑）。

### 怎么证明修好了

之后几十次重启（包括最终验收前的 `stop.sh` + `demo.sh`）没有再出现连接被拒绝。

### 面试怎么讲

S：脚本重启服务后偶发请求失败。T：找出竞态。A：从日志里对上旧进程的 pid，把停止改成等待进程真正退出。R：重启变得确定，而且停止只作用于自己起的进程。

## q07-retry-duplicates 客户端重试建出多条记录（生产典型，失败对照）

### 现象

关掉幂等保护（`RM_LAB_SABOTAGE=no_idempotency`），八个并发的相同请求：

```text
FAILED tests/test_step01_idempotency.py::test_concurrent_retries_create_exactly_one_record
AssertionError: 8 records for one idempotency key
```

### 在哪里

[rmflow/intake.py](../rmflow/intake.py)，锚点 `idempotency-guard`；「先查再插」的写法在 [snippets/intake_before.py](problems/snippets/intake_before.py)（锚点 `before-idempotency`）。

### 怎么定位

- 八个请求同时执行「查这个键有没有」，都查到没有，于是都插入。这是典型的 check-then-act 竞态。
- 数据库层面没有任何约束挡住它。

### 怎么解决

先 `INSERT ... ON CONFLICT DO NOTHING` 占住 `(client_id, key)`，插入成功的那一个在同一事务里干活；没插进去的用 `SELECT ... FOR UPDATE` 等对方提交后重放响应；同 key 不同请求体返回 422。record id 由 key 派生，就算有请求绕过也会撞主键。

### 怎么证明修好了

保护打开时同一个测试是绿的：七个 200（带 `Idempotent-Replay: true`）、一个 201，库里一条记录。

### 面试怎么讲

S：客户端超时重试会重复建记录，下游重复审核。T：保证重试只算一次。A：用数据库唯一约束做幂等，先占键再干活，并发重试等待并重放第一次的响应。R：八个并发重试只产生一条记录，关掉保护测试立即变红。

## q08-modulo-reshuffle 扩容一台，七成五的记录换主人（生产典型，失败对照）

### 现象

```text
AssertionError: moved 75.38% of keys, expected about 25%
```

（`RM_LAB_SABOTAGE=modulo_hash`，`tests/test_step03_ring.py::test_scale_out_moves_about_one_over_n_plus_one`）

### 在哪里

[rmflow/ring.py](../rmflow/ring.py)，锚点 `ring-lookup`；取模写法在 [snippets/modulo_before.py](problems/snippets/modulo_before.py)（锚点 `before-modulo`）。

### 怎么定位

取模时 N 一变，几乎每个 key 的余数都变。每一次换主人都是一次所有权交接，交接窗口里才会出现乱序和并发处理。

### 怎么解决

一致性哈希环，每个 worker 128 个虚拟节点，key 顺时针找第一个点。扩容只搬新节点前面的弧。

### 怎么证明修好了

同一测试打开保护：20000 个 key 搬走 0.283，全部搬给 w4；在跑着的系统上 606 个真实 record id 搬走 0.2789。基准表见 `docs/results/ring-bench.md`。

### 面试怎么讲

S：worker 扩容时大量记录换主人。T：让扩容只影响必要的那一部分。A：换成带虚拟节点的一致性哈希，并写了一个比较取模的迁移比例测试。R：三台扩到四台搬走约四分之一，而取模要搬四分之三，测试能区分两者。

## q09-out-of-order 第五版比第一版先处理（生产典型，失败对照）

### 现象

```text
assert [5, 2, 6, 1, 3, 4, ...] == [1, 2, 3, 4, 5, 6]
```

（`RM_LAB_SABOTAGE=no_order_gate`）；关掉锁（`no_lock`）时：`assert 2 == 1`，同一时刻两个 worker 在处理同一条记录。

### 在哪里

[rmflow/worker.py](../rmflow/worker.py)，锚点 `order-gate`、`worker-handle`；锁在 [rmflow/locks.py](../rmflow/locks.py)，锚点 `record-lock`；无闸门写法在 [snippets/order_before.py](problems/snippets/order_before.py)（锚点 `before-order`）。

### 怎么定位

SQS 标准队列会乱序、会重复；扩容瞬间新旧两个 owner 都可能收到同一条记录的步骤。只靠「消息到了就处理」，顺序和互斥都没有保证。

### 怎么解决

按 seq 设闸门：做过的丢掉、下一个才做、更大的放回队列等；每条记录一把 Redis 锁，拿锁时 `INCR` 出 fencing token，写库带 `WHERE fence < token`，锁过期的旧 owner 写不进去。

### 怎么证明修好了

保护打开：乱序投递 `5,2,6,1,3,4,2` 的应用顺序是 `[1..6]`；两个 owner 并发时 `max workers inside one record at once: 1`；`test_stale_owner_is_fenced_out_after_its_lock_expired` 断言旧 owner 被 fence 掉。

### 面试怎么讲

S：同一条记录的多个版本可能乱序、并发处理。T：保证每条记录的步骤严格有序且同一时刻只有一个 worker。A：用版本号闸门代替队列顺序，用 Redis 锁加 fencing token 防并发和锁过期。R：乱序和并发两种失败对照都能稳定复现并被修复挡住。

## q10-no-auto-rollback 新路由出错还在继续放量（生产典型，失败对照）

### 现象

```text
[ERROR]   RolloutPolicyTest.errorRegressionRollsBackToZeroWithinFiveSeconds:52 [never rolled back]
```

（`-Drm.lab.sabotage=no_rollback`）

### 在哪里

[RolloutPolicy.java](../routing-svc/src/main/java/dev/reviewmesh/rollout/RolloutPolicy.java)，锚点 `rollback-decision`；只会前进的版本在 [snippets/rollout_before.java](problems/snippets/rollout_before.java)（锚点 `before-rollout`）。

### 怎么定位

控制器只看「待够时间没有」，不看错误率。新版本出错时，回退完全依赖人发现。

### 怎么解决

每半秒看 v2 最近十秒的结果：样本至少五个、错误率超过百分之五就回到 0%，并写入原因；健康待满十秒才升档。v2 单次失败当场退回 v1，用户无感。

### 怎么证明修好了

保护打开：`fault at 3000 ms, rolled back at 3500 ms`；在跑着的系统上注入四成故障，`rolled back 1.7s after the fault: v2 error rate 11.4% > 5.0% over the last 10s (n=35)`。

### 面试怎么讲

S：新路由逻辑灰度上线。T：出问题时不依赖人工发现就退回去。A：用滑动窗口错误率驱动的纯函数控制器，带最小样本数，并用假时钟测试回滚时限。R：故障注入后一到两秒内自动回到 0%，关掉保护测试立即变红。
