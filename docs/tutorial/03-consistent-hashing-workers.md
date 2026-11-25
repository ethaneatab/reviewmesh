# 第 3 章 把记录分给多个 worker，一条记录的步骤始终有序（consistent hashing）

> 本章讲解视频：[../videos/p3-partition.mp4](../videos/p3-partition.mp4)

## 这一章解决什么问题？

一个 worker 处理不过来，就要多开几个。可是同一条记录会有好几个步骤：第 1 版进来，客户端又交了第 2 版、第 3 版。
如果这些步骤落在不同的 worker 上并行跑，第 3 版可能比第 1 版先处理完，最后留下的是旧数据。
所以要两件事：**同一条记录永远交给同一个 worker；加 worker 的时候，尽量少搬家。**

## 为什么不用 hash % N？

假设：`owner = hash(record_id) % N`，简单直接。
问题出在扩容。N 从 3 变成 4，几乎每个 key 的余数都变了。我们实测了，`hash % N` 从 3 到 4 搬走了 75.1% 的 key（`docs/results/ring-bench.md`）。
每搬一个 key，就有一次所有权交接，交接期间就有乱序和重复的风险。搬得越多，风险越大。

一致性哈希（`rmflow/ring.py`，锚点 `ring-lookup`）：

- 每个 worker 在 64 位的环上放 128 个虚拟节点（virtual nodes）。
- key 落在环上某一点，顺时针找到的第一个虚拟节点就是它的主人。
- 新 worker 只接管自己那些点前面的一小段弧，所以只搬走大约 1/(N+1) 的 key，而且**只搬给新来的那个**。

## 实测：搬走多少？

`.venv/bin/python scripts/ring_bench.py`，五组各两万个随机 id，取中位数（节选）：

| N → N+1 | 理想值 1/(N+1) | 环，128 个虚拟节点 | hash % N |
|---|---|---|---|
| 3 → 4 | 0.250 | 0.277 | 0.751 |
| 4 → 5 | 0.200 | 0.175 | 0.800 |
| 8 → 9 | 0.111 | 0.103 | 0.889 |

在跑着的系统上点一次扩容（`POST /v1/ring/scale-out`），数据库里 606 个真实 record id 里有 169 个换了主人，比例 0.2789，全部搬给了 w4：

```json
{"change": {"epoch": 1, "before": ["w1","w2","w3"], "after": ["w1","w2","w3","w4"]},
 "keys_checked": 606, "moved": 169, "moved_fraction": 0.2789, "expected_fraction": 0.25,
 "moved_sample": [{"key": "rec_a44cc425ee20275b", "from": "w2", "to": "w4"}, ...]}
```

比 0.25 高一点，是因为 128 个虚拟节点不完全均匀：w4 恰好拿到的弧长一些。虚拟节点开到 256，3 到 4 的中位数是 0.253。

## 消息怎么到 worker 手里？

pipeline 里的 dispatcher（`rmflow/pipeline.py`，锚点 `dispatch-partition`）读 `rm-intake`，算出 owner，把消息转进那个 worker 自己的队列 `rm-work-w2`。
时间线上会多一条 `PARTITIONED`，带着环上的位置（真实输出）：

```text
PARTITIONED   dispatcher {"ring": "consistent", "angle": 57.94, "epoch": 0, "owner": "w2", "vnode": "w2#27", "members": ["w1","w2","w3"], "vnode_angle": 59.624}
WORKER_PICKED worker:w2  {"epoch": 0, "worker": "w2", "fence_token": 1, "receive_count": 1}
APPLIED       worker:w2  {"token": 1}
```

## 扩容的那一瞬间，会不会两个 worker 同时处理一条记录？

会，如果什么都不做。扩容前排进 w2 队列的消息，扩容后 w2 才收到；同时 w4 也收到了同一条记录的下一步。
所以 `Worker.handle`（锚点 `worker-handle`）做了三层：

1. **不是我的就转走。** 收到消息先按当前的环算 owner，不是自己就转发给新 owner，时间线记 `FORWARDED`。
2. **Redis 锁**（锚点 `record-lock`）。处理前 `SET rm:lock:<id> NX PX 15000`。拿不到说明上一个 owner 还在做，消息放回队列一秒后再来。
3. **fencing token**（锚点 `fenced-commit`）。锁会过期，比如旧 worker 卡住了十几秒。所以每次拿锁都 `INCR` 出一个递增的 token，写库时带上 `WHERE fence < token`。过期的旧 worker 再来写，影响行数是零，直接作废。

## 顺序靠什么保证？

SQS 标准队列不保证顺序，还会重复投递。所以 worker 不信队列的顺序，只信 seq（锚点 `order-gate`）：

- `seq <= last_seq`：做过了，丢掉（这也挡住了第 2 章 reconciler 补发造成的重复）。
- `seq == last_seq + 1`：就是下一步，做。
- 更大：前面还有一步没到，放回队列等一等。

## 怎么证明？（能失败的对照）

| 测试 | 关掉什么 | 关掉后的真实输出 |
|---|---|---|
| `test_scale_out_moves_about_one_over_n_plus_one` | `modulo_hash` | `AssertionError: moved 75.38% of keys, expected about 25%` |
| `test_steps_apply_in_seq_order_even_when_delivered_shuffled` | `no_order_gate` | `assert [5, 2, 6, 1, 3, 4, ...] == [1, 2, 3, 4, 5, 6]` |
| `test_two_owners_during_a_handoff_never_overlap_on_one_record` | `no_lock` | `assert 2 == 1`（同一时刻有两个 worker 在同一条记录里） |

打开保护时这三条都是绿的：乱序投递 `5, 2, 6, 1, 3, 4, 2` 最后的应用顺序是 `[1, 2, 3, 4, 5, 6]`；两个 owner 抢同一条记录，同时在里面的最多一个。

## 怎么 checkout 到这一步跑起来

```bash
git checkout step-03
./scripts/demo.sh                              # 多了 w1..w3（8892-8894）和待命的 w4（8895）
.venv/bin/python scripts/seed_records.py 600   # 给环上放一些 key
curl -s -X POST localhost:8890/v1/ring/scale-out
.venv/bin/python -m pytest                     # 20 passed
```
