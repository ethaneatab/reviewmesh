# 讲解视频

每个教学阶段一段短片，`/learn` 页面里每个阶段旁边的「看讲解视频」播放的就是这里的文件。清单见 [`video/parts.json`](../../video/parts.json)：

| 文件 | 内容 | 对应教程 |
|---|---|---|
| [`p1-intake.mp4`](p1-intake.mp4) | 收件和幂等键 | — |
| [`p2-s3-lambda.mp4`](p2-s3-lambda.mp4) | S3 触发 Lambda，消息进 SQS | — |
| [`p3-partition.mp4`](p3-partition.mp4) | 一致性哈希分区与扩容 | — |
| [`p4-route.mp4`](p4-route.mp4) | 校验与 Java 路由 | — |
| [`p5-review.mp4`](p5-review.mp4) | 人工审核、审计与导出 | — |
| [`p6-migration.mp4`](p6-migration.mp4) | expand / contract 表迁移 | — |
| [`p7-rollout.mp4`](p7-rollout.mp4) | 分阶段放量与自动回滚 | — |
| [`p8-observe.mp4`](p8-observe.mp4) | 可观测、面试题与日常问题 | — |

画面由 `video/record.mjs` 在真实页面上录制（会话里的数据都是这次真实请求产生的），红框标出每一步该看的地方；旁白来自 `video/narration.json`。旁白是本地 TTS 合成的（CosyVoice 2 自带的示例音色，不调任何云端 API），成片用本地 whisper 逐段回验过念的是稿子上的话。

## 日常问题（`problems/`）

每个问题一段代码讲解：先看修复前的写法和现象，再看修复后的写法，讲到哪几行就用红框框出哪几行。内容来自 [`video/problems.walk.json`](../../video/problems.walk.json)（由 `scripts/build_problem_videos.py` 按锚点从源码生成），问题的来龙去脉见 [`docs/problems.md`](../problems.md)。

- [`q01-lambda-dist-info.mp4`](problems/q01-lambda-dist-info.mp4) — Lambda 一直起不来
- [`q02-backfill-erases-claims.mp4`](problems/q02-backfill-erases-claims.mp4) — 回填差点抹掉新版本的认领
- [`q03-contract-before-backfill.mp4`](problems/q03-contract-before-backfill.mp4) — 删列跑早了会怎样
- [`q04-stale-jar-constructor.mp4`](problems/q04-stale-jar-constructor.mp4) — 服务起不来：找不到默认构造函数
- [`q05-search-path.mp4`](problems/q05-search-path.mp4) — 表明明建好了，SQL 却说语法错误
- [`q06-stop-race.mp4`](problems/q06-stop-race.mp4) — 重启以后请求打到了正在退出的旧进程
- [`q07-retry-duplicates.mp4`](problems/q07-retry-duplicates.mp4) — 客户端重试，一份文档建了八条记录
- [`q08-modulo-reshuffle.mp4`](problems/q08-modulo-reshuffle.mp4) — 扩容一台 worker，七成五的记录换了主人
- [`q09-out-of-order.mp4`](problems/q09-out-of-order.mp4) — 第五版比第一版先处理完
- [`q10-no-auto-rollback.mp4`](problems/q10-no-auto-rollback.mp4) — 新路由逻辑出错，没人发现就一直放量
