# 第 6 章 不停机改表：expand / contract 迁移和 API 兼容性测试

> 本章讲解视频：[../videos/p6-migration.mp4](../videos/p6-migration.mp4)

## 这一章解决什么问题？

第 4 章为了快，`review_tasks.reviewer` 是一个文本列，存审核员的用户名。现在要把它改成外键 `reviewer_id`，指向新表 `reviewers`。
难点不在 SQL，而在**上线过程中旧版本和新版本的服务会同时跑**：滚动发布时总有一段时间，一半实例是旧代码，一半是新代码。任何一步都不能让其中一半出错，也不能让老客户端（只认 `reviewer` 这个字段）读到坏数据。

## 为什么不能一条 ALTER 直接改？

假设：一个迁移里加 `reviewer_id`、回填、删 `reviewer`，然后发新版本。
迁移跑完的那一刻，旧实例还在跑，它的 SQL 里有 `reviewer`，立刻全部报错。反过来先发新代码，新代码又找不到 `reviewer_id`。
所以要拆成五步，每一步只往前挪一小格，而且**每一步相邻的两个版本都能同时跑**。

## 五步分别是什么？

代码里把「这个版本走到哪一步」叫做 phase（`routing-svc/.../migration/ReviewerPhase.java`）：

| 步骤 | 表结构 | 同时在跑的版本 | 读哪一列 | 写哪一列 |
|---|---|---|---|---|
| 1 expand | V2：加 `reviewers` 表和可空的 `reviewer_id` | LEGACY + DUAL_WRITE | 文本 | 新版两列都写 |
| 2 backfill | 不变 | DUAL_WRITE | 文本 | 两列 |
| 3 切读 | 不变 | DUAL_WRITE + READ_NEW | 新版读 id | 两列 |
| 4 只写新列 | 不变 | READ_NEW + NEW_ONLY | id | 新版只写 id |
| 5 contract | V3：删 `reviewer` | NEW_ONLY | id | id |

所有碰到审核员的 SQL 都在 `TaskRepository` 的三个小函数里拼（锚点 `phase-sql`）：读用哪一列、写哪几列、「是不是这个人认领的」看哪一列。

expand 的迁移（`V2__expand_reviewer_id.sql`）只加不改。外键先 `NOT VALID` 再 `VALIDATE`：大表上这样不会在检查每一行时一直持有强锁。

## 回填有什么坑？（真实踩到的）

回填（`MigrationService.backfill`，锚点 `backfill`）分批跑，可以反复跑。第一版的「还有多少行没回填」是这么判断的：文本列和 id 列一个空一个不空，就算没对齐。
`MigrationCompatTest` 第一次跑就红了：

```text
MigrationCompatTest.everyStepRunsOldAndNewSideBySide
expected: 0L
 but was: 1L
```

- 假设：回填漏了一行。打印那一行，是 NEW_ONLY 版本刚认领的任务，`reviewer_id` 有值，文本是空的。
- 这不是漏，这正是 NEW_ONLY 该写出来的样子。判断条件错把新版本的正常数据当成了脏数据。
- 更糟的是，回填里还有一句「文本空、id 不空就把 id 清掉」，用来修旧版本取消认领时只清了文本的情况。如果在 NEW_ONLY 上线之后跑，它会把新版本的认领全部抹掉。
- 修法：「没对齐」只看「文本有值，但 id 没有或对不上」；清 id 那一句只允许从 DUAL_WRITE 版本里跑。

## 如果有人提前跑了 contract 呢？

V3 第一段是一个守卫：还有没回填的行就 `RAISE EXCEPTION`，整个迁移回滚，列不会被删。在真实的演示库上就撞到过一次（真实日志）：

```text
Migrating schema "review" to version "3 - contract drop reviewer text"
ERROR: contract blocked: 2 review_tasks rows are not backfilled (POST /v1/migration/backfill)
Migration of schema "review" to version "3 - contract drop reviewer text" failed! Changes successfully rolled back.
```

然后按正确的顺序在演示库上走了一遍（`scripts/restart_routing.sh`，真实输出）：

```text
$ RM_FLYWAY_TARGET=2 RM_MIGRATION_PHASE=DUAL_WRITE scripts/restart_routing.sh
phase DUAL_WRITE versions ['1', '2'] pending 2
backfill batch=1:   {"updated":1,"remaining":1}
backfill batch=500: {"updated":1,"remaining":0}
$ RM_MIGRATION_PHASE=NEW_ONLY scripts/restart_routing.sh
phase NEW_ONLY versions ['1', '2', '3'] text col False reviewers 1
{'id': 5, 'reviewer': 'rita', 'reviewer_id': 1, 'status': 'APPROVED'}
```

最后一行很关键：文本列已经删了，老客户端读到的 `reviewer` 还是 `rita`，它是从 `reviewers.handle` 拼回来的。

## 怎么证明「没有破坏兼容」？

两层：

1. **新旧版本并行的测试**（`MigrationCompatTest`，锚点 `test-expand-contract`）。在一个单独的库 `reviewmesh_migr` 上，用 Flyway 一步一步迁到 V1、V2、V3。每一步造两个 `TaskRepository`，一个旧 phase、一个新 phase，共用同一张表：旧的能读到新的写的，新的能读到旧的写的，旧的能把新的认领的任务做完。最后一步还断言 V1 的 SQL 在 V3 上确实会失败，说明「先下线旧版本再 contract」这个顺序是必要的。
2. **API 契约快照**。`contracts/task.v1.json` 是第 5 章时 `GET /v1/tasks/{id}` 的原样输出。每一步都把任务的 JSON 和这个快照比：字段少了、类型变了就红；多出 `reviewer_id` 没关系。

另外两个测试：`contractRefusesToRunBeforeTheBackfill`（守卫真的拦得住），`skippingAPhaseIsCaught`（LEGACY 直接和 NEW_ONLY 并存时，旧版本看不到新版本的认领，所以不能跳步）。

## 怎么 checkout 到这一步跑起来

```bash
git checkout step-06
(cd routing-svc && JAVA_HOME=/opt/homebrew/opt/openjdk@21 mvn -q test)    # 12 个 Java 测试
# 在已有数据的库上一步步迁：
RM_FLYWAY_TARGET=2 RM_MIGRATION_PHASE=DUAL_WRITE scripts/restart_routing.sh
curl -X POST 'localhost:8891/v1/migration/backfill?batch=500' -H "Authorization: Bearer <ops token>"
RM_MIGRATION_PHASE=NEW_ONLY scripts/restart_routing.sh
```
