# 第 7 章 新路由逻辑分阶段放量，错误率一高自动回滚

> 本章讲解视频：[../videos/p7-rollout.mp4](../videos/p7-rollout.mp4)

## 这一章解决什么问题？

路由规则要升级：v2 会看队列积压，忙的队列溢出到 `shared-review`，优先级分得更细（`RuleEngineV2`，锚点 `routing-v2`）。
新逻辑一次性全量上线，出了 bug 就是所有文档都路由错。所以：**先给 1% 的记录用，没事再 10%、50%、100%；一旦新版本错误率上去，不等人发现，自动退回 0%，并把原因记下来。**

## 放量比例怎么落到具体某条记录上？

feature flag `routing-v2` 的比例存在 Postgres 的 `rollout_state` 表（`V4__rollout.sql`）。
每条记录算一个固定的桶号：`CRC32(record_id) % 100`。桶号小于比例就走 v2（`RoutingService.choose`，锚点 `flag-choose`）。同一条记录的重试永远落在同一个桶里，不会一会儿 v1 一会儿 v2。
v2 抛异常时，这一次请求立刻退回 v1，用户无感；但这次失败会被记进 v2 的错误统计。

## 控制器怎么判断？

`RolloutPolicy.tick`（锚点 `rollback-decision`）是一个纯函数，每半秒被调一次（`RolloutService.tick`，锚点 `rollout-tick`）：

1. 只看 v2 最近十秒的结果。少于五次不下结论，样本太少的错误率没意义。
2. 错误率超过百分之五：比例改成 0，状态 `ROLLED_BACK`，写一条事件，原因里带上错误率、阈值和样本数。
3. 健康地待满十秒：升到下一档。

为什么写成纯函数？因为「几秒之内回滚」要能在测试里用假时钟断言，不能靠真的等。

## 怎么证明它真的会回滚？（能失败的对照）

`RolloutPolicyTest.errorRegressionRollsBackToZeroWithinFiveSeconds`（锚点 `test-rollback`）：模拟每秒五十个 v2 请求，第三秒开始三成请求失败，断言五秒内比例回到 0。真实输出：

```text
fault at 3000 ms, rolled back at 3500 ms (500 ms later)
Tests run: 4, Failures: 0, Errors: 0, Skipped: 0 -- in dev.reviewmesh.RolloutPolicyTest
```

把自动回滚关掉（`-Drm.lab.sabotage=no_rollback`）再跑，必须红：

```text
[ERROR]   RolloutPolicyTest.errorRegressionRollsBackToZeroWithinFiveSeconds:52 [never rolled back]
[ERROR] Tests run: 4, Failures: 1, Errors: 0, Skipped: 0
```

## 在跑着的系统上演练一次

放量需要流量。`POST /v1/rollout/traffic`（`rmflow/traffic.py`）用 dry-run 请求打真实的路由接口：走同一条决策路径，但不写库。
`tests/test_step07_rollout.py` 把比例推到 10%，开流量，注入四成故障，计时（真实输出）：

```text
rolled back 1.7s after the fault: v2 error rate 11.4% > 5.0% over the last 10s (n=35)
```

为什么错误率只有百分之十一，而不是注入的四十？因为十秒窗口里还有注入故障之前的成功请求，故障越久，比例越接近四十。只要越过百分之五就回滚了，所以不用等它涨上去。

前端 `/rollout` 页是这个过程的控制台：放量阶梯、窗口内的样本数和错误率、v2 每秒错误率的曲线和阈值虚线、每一次放量和回滚的记录。`e2e/rollout.spec.ts` 从界面点一遍：开始、下一档、模拟流量、注入故障，等状态变成 `ROLLED_BACK`。

## 怎么 checkout 到这一步跑起来

```bash
git checkout step-07
./scripts/demo.sh
open http://127.0.0.1:5189/rollout
(cd routing-svc && JAVA_HOME=/opt/homebrew/opt/openjdk@21 mvn -q test -Dtest=RolloutPolicyTest -Drm.lab.sabotage=no_rollback)   # 红
```
