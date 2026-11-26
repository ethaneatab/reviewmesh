# AI 辅助开发：怎么验证

这个仓库的代码大部分是在 AI 编程助手的帮助下写出来的。AI 写的代码看起来总是很像对的，所以这里写清楚：每一类改动靠什么证明它对，而不是靠「看起来没问题」。

## 一、每次改动都要过的检查

| 检查 | 命令 | 抓什么 |
|---|---|---|
| Python 静态检查 | `.venv/bin/ruff check rmflow tests scripts lambdas` | 未用变量、异常链丢失（B904）、可疑写法 |
| Python 类型检查 | `.venv/bin/mypy rmflow` | `fetchone()` 可能为 None 却直接取下标这类问题（真的抓到过两处，见下） |
| Java 静态分析 | `cd routing-svc && mvn -q compile spotbugs:check` | 空指针、资源泄漏、可变状态暴露 |
| TypeScript 类型检查 | `cd frontend && npx tsc -b --noEmit` | 接口字段和组件 props 对不上 |
| 锚点 | `.venv/bin/python scripts/check_anchors.py` | 页面、文档、视频引用的源码行不存在或过期 |
| 旁白 | `.venv/bin/python scripts/check_narration.py`、`scripts/build_problem_videos.py` | 旁白里混进代码符号和数字；高亮行号越界 |

这些都写进了 `.github/workflows/ci.yml` 的 `checks` 任务。

## 二、测试本身也要被验证

AI 很擅长写「永远绿」的测试。所以关键保护都有一个开关（`rmflow/lab.py`、Java 的 `Lab`），`scripts/failing-controls.sh` 把每个保护关掉跑一次、打开跑一次：关掉必须红，打开必须绿。五个对照的实测输出在 `docs/results/failing-controls.txt`，也贴在 README。

## 三、review 时专门看什么

AI 写的代码里，下面这些地方最容易「看起来对、其实错」，review 时逐条看：

1. **先查再写**。任何「先 SELECT 判断，再 INSERT/UPDATE」的地方，问一句并发时会怎样。幂等键和认领都改成了靠约束或带条件的单条语句。
2. **重试**。有没有上限、退避、抖动；4xx 是否被错误地重试；重试后的副作用是否幂等。
3. **迁移**。新代码能不能跑在旧表上，旧代码能不能跑在新表上。真实例子：回填条件第一版把新版本的正常数据当成脏数据（`docs/problems.md` q02），是并行测试抓到的，不是 review 看出来的。
4. **时间**。用墙钟做断言的测试会不稳；灰度回滚的时限用假时钟测纯函数。
5. **报错原文**。AI 总结的报错原因常常比原文更「合理」但是错的。q01 和 q05 都是读了原文才定位的。

## 四、真实抓到的例子

- mypy：`rmflow/worker.py` 和 `rmflow/ops.py` 里对 `fetchone()` 的结果直接取下标，可能是 None。已改成先判断。
- ruff B904：`except` 里重新抛 `HTTPException` 时丢了原异常，已补 `from exc`。
- 迁移并行测试：`MigrationCompatTest` 第一次运行红，定位到 q02。
- e2e：学习页源码链接的测试会读取本地文件，确认链接里的行号确实落在锚点标记之间。

## 五、哪些是人必须做的

AI 不知道哪些数字是真的。README 里的每个数字都来自仓库里能重跑的命令（`scripts/ring_bench.py`、`scripts/explain_paths.py`、测试输出），简历上的数字不写进 README。
