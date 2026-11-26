# reviewmesh

一个文档审核工作流的重建：收件、校验、按一致性哈希分区的 worker、Java 路由与人工审核队列、审计，外加 expand/contract 表迁移和按错误率自动回滚的分阶段发布；Python FastAPI + Java Spring Boot + React/TypeScript，本地用 LocalStack 4.9 跑 S3 / Lambda / SQS。

![learn mode preview](docs/learn-preview.gif)

完整讲解视频：[Release learn-video](../../releases/tag/learn-video) · 分章教程：[docs/tutorial/](docs/tutorial/) · 面试题：[docs/interview.md](docs/interview.md) · 日常问题：[docs/problems.md](docs/problems.md)

## 架构

```mermaid
flowchart LR
  C[客户端<br/>Idempotency-Key] -->|POST /v1/records| I[intake API<br/>FastAPI :8890]
  I -->|同一事务: 幂等键+记录| PG[(Postgres<br/>intake / review)]
  I -->|PutObject| S3[(S3 inbox)]
  S3 -->|ObjectCreated| L[Lambda rm-s3-intake]
  L -->|intake.v1| Q1[[SQS rm-intake]]
  R[reconciler<br/>STORED > 20s] -.fallback.-> Q1
  Q1 --> D[dispatcher<br/>一致性哈希环]
  D --> W1[[rm-work-w1]] & W2[[rm-work-w2]] & W3[[rm-work-w3]] & W4[[rm-work-w4 待命]]
  W1 & W2 & W3 & W4 --> WK[worker :8892-8895<br/>seq 闸门 + Redis 锁 + fencing]
  WK -->|REST routing-decision.v1<br/>有限重试 + fallback| J[routing-svc<br/>Spring Boot :8891]
  WK -->|handoff.v1| Q2[[SQS rm-handoff]] --> J
  J -->|flag routing-v2<br/>1→10→50→100%| J
  J -->|outbox decision.v1| Q3[[SQS rm-decisions]] --> X[exporter] --> S3E[(S3 exports<br/>CSV / Parquet)]
  UI[React :5189<br/>队列 · 时间线 · 哈希环 · 发布台 · 运维 · 教学] --> I & J
  WK & D & R -.-> RD[(Redis<br/>环成员 · 锁 · 热点缓存)]
```

每个箭头上的消息和请求都有契约快照（[contracts/](contracts/)），两边的测试都读同一份文件。

## 怎么跑起来

```bash
./scripts/demo.sh                            # Postgres/Redis/LocalStack + bootstrap + Java + API + pipeline + 4 workers + 前端
.venv/bin/python scripts/seed_records.py 600 # 可选：给哈希环页放一些 key
open http://127.0.0.1:5189/learn             # 教学页：点「提交样例」
./scripts/stop.sh                            # 按 pid 停掉 demo.sh 起的进程
docker-compose -p reviewmesh stop            # 停容器（down -v 清数据）
```

| 服务 | 端口 |
|---|---|
| intake API（FastAPI，含 `/learn/api`、`/metrics`、`/videos`） | 8890 |
| routing-svc（Java：路由、审核队列、审计、灰度、迁移状态） | 8891 |
| worker w1–w3 / 待命的 w4（管理接口 `/state` `/join` `/leave` `/metrics`） | 8892–8895 |
| Prometheus / Grafana（可选 `--profile obs`） | 8896 / 8897 |
| 前端（Vite） | 5189 |
| Postgres / Redis / LocalStack | 54390 / 63590 / 45690 |

演示账号只在 `RM_SEED_DEMO=1` 时创建：rita（审核员）、sam（资深审核员）、olive（运维），密码是「用户名-demo」。
本地用 JDK 21 编译和运行 Java（`maven.compiler.release=17`）；Python 3.11，项目自己的 `.venv`。

## 技术选型和理由

- **幂等键落 Postgres，靠主键挡**：和业务数据同一事务提交；并发重试等对方提交后重放响应（`rmflow/intake.py`）。
- **S3 → Lambda → SQS**：文件落地这个事实驱动后续流程，收件接口不被后端拖慢；Lambda 丢事件由 reconciler 兜底。
- **一致性哈希（128 个虚拟节点）**：同一条记录固定在一个 worker 上按 seq 执行，扩容只搬约 1/(N+1)；交接期间用 Redis 锁 + fencing token。
- **路由同步 REST，交接异步 SQS**：worker 需要路由结果才能往下走；交接后不必等审核侧。
- **transactional outbox**：审核结论和下游消息原子提交。
- **Flyway + 分阶段 SQL**：`reviewer` 文本列到 `reviewer_id` 外键的五步迁移，每一步相邻两个版本并行可用；删列前有守卫。
- **纯函数的灰度控制器**：错误率窗口、最小样本数、假时钟测试回滚时限。
- **LocalStack 4.9 钉死版本**：新版需要 auth token。

## 测试

RESULTS_PLACEHOLDER

## 仓库实测指标

所有数字都能用仓库里的命令重跑；测量环境是本机 colima（4 核 / 6 GiB，与其他几个项目共享）。延迟类的数字只说明链路，不作为性能结论。

METRICS_PLACEHOLDER

## What this is not / 局限

- 不是性能基准：没有做压测，没有吞吐数字。
- 灰度的滑动窗口在 Java 进程内存里，多实例时要放进共享存储或指标系统。
- fencing token 由 Redis `INCR` 生成；Redis 丢数据时 token 会回退（会被库里更大的 fence 拒绝，但需要人工处理）。
- DLQ 只能看（运维页、告警），没有一键重放。
- JWT 是共享 HS256 密钥，默认值是明显的本地占位；生产应换成 KMS/Secrets Manager 和真正的身份服务。
- Lambda 部署用 boto3 脚本（`rmflow/bootstrap.py`），不是 IaC。
- CI（`.github/workflows/ci.yml`）写好了，但这个仓库还没推到 GitHub，CI 从没在 GitHub 上跑过；本地等价命令都跑通了。
- 简历里的数字是在公司里的结果，这里一个都没写；面试题「简历对应」一节说明了怎么分开讲。

## 其他文档

- [docs/tutorial/](docs/tutorial/)：八章，每章对应一个 git tag（`step-01` … `step-08`）
- [docs/ai-dev-verification.md](docs/ai-dev-verification.md)：AI 辅助开发怎么验证
- [docs/results/](docs/results/)：环基准、EXPLAIN 计划、失败对照的原始输出

## License

MIT
