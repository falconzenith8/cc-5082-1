# 比赛时钟推进方案决策说明

## 1. 两个候选方案

| 维度 | 固定逻辑步 `FixedStepDriver` | 按事件跳到下一期限 `EventJumpDriver`（选定） |
|---|---|---|
| 推进方式 | 时间轴量化为 `step` 网格，每个步边界固定醒来 | 只在下一意图墙钟点或赛钟零点醒来 |
| 精度 | 承诺时刻被量化，误差上界 ≈ 一个步长 | 无量化，承诺时刻精确到浮点秒 |
| 空闲开销 | 与赛事墙钟长度 / `step` 成正比，长暂停期间持续空转 | 只与真实期限数相关，非 LIVE 期间零醒来零 tick |
| 裁决顺序 | 复用同一 `RuleEngine` 的 `(period, 节长-commit_at, TYPE_RANK, seq)` | 同左，规则内核没有分叉 |
| 调参 | `step` 越小越准但开销越大，二者不可兼得 | 无步长参数，精度与空闲开销解耦 |

两者都实现统一接口 `ClockDriver`（`sport/drivers/base.py`），消费同一份
`IntentFeed`（`sport/drivers/scenarios.py`），规则裁决只调用同一个
`RuleEngine`，因此差异严格限定在“时间如何推进”。

## 2. 统一约定（任何不一致都可追到具体迁移）

- **时间单位**：全部为秒（float）。墙钟是单调秒，赛钟 `quarter_seconds` /
  `ot_seconds` 也是秒，见 `scenarios.UNIT_NOTES`。
- **得分承诺约定**：`commit_at = 承诺瞬间的有效赛钟剩余秒`（倒计时，
  `0.0` 即鸣笛同刻）。命令在意图声明的墙钟点执行，`commit_at` 由内核当场
  从赛钟读取，场景只给 `ref_commit_at` 做精度对照，不反向注入承诺时刻。
- **排序约定**：`(period, period_length-commit_at, TYPE_RANK, seq)`，
  两个驱动共用同一份折叠代码，同刻多期限顺序天然一致。
- **不一致追踪**：`measurements/migration_trace.md` 把每条差异定位到
  具体时钟迁移（业务锚点 `note` + `wall_at` + 剩余值）或具体意图标签的
  裁决分歧；全量 tick 台账在 `measurements/raw_runs.json`。

## 3. 测量证据（可复跑，不凭一次计时下结论）

复跑命令：

```
python -m sport.drivers.benchmark     # 写 measurements/{raw_runs,summary}.json + migration_trace.md
python -m sport.drivers.tests          # 43 项驱动对照断言
python -m sport.http_smoke             # 两种调度方案各打一场常规赛+加时
```

每个场景重复 7 次（`benchmark.RUNS`），墙钟是确定性虚拟秒而非
`time.monotonic`，报告均值与总体标准差；标准差用于暴露环境抖动，
不用单次计时证明性能优劣。关键结果（来自最近一次 `summary.json`）：

| 场景 | 驱动 | 醒来次数 | 最大承诺误差 |
|---|---|---:|---:|
| 长暂停（30s 演出） | fixed@1s / fixed@0.25s / event_jump | 40 / 160 / **5** | 0 / 0 / 0 |
| 末秒压哨 | fixed@1s | 22 | **0.5s（真实出手被误拒）** |
| 末秒压哨 | fixed@0.25s / event_jump | 88 / **6** | 0 / 0 |
| 亚步暂停/恢复 | fixed@1s / fixed@0.25s / event_jump | 22 / 88 / **4** | 0.4 / 0.15 / **0** |
| 完整四节+加时 | fixed@1s / fixed@0.25s / event_jump | 91 / 364 / **13** | 0 / 0 / 0 |
| 高频中断（每 0.2s） | fixed@1s / event_jump | **22** / 41 | 0 / 0 |

真实 HTTP 入口（`http_smoke`，四节+加时）：事件跳 8 次 tick，
旧 50ms 固定轮询 276~277 次 tick，两者最终比分、阶段、回合、球权完全一致。

### 三个规定场景的结论

1. **末秒得分**：粗固定步把墙钟 19.5 的出手量化到 20.0 网格，鸣笛先折叠，
   真实出手被 `shot_requires_live` 拒绝（误差 0.5s 可在
   `migration_trace.md` 的 `buzzer_zero` 锚点追到）；事件跳在 19.5 精确
   处理，出手在 LIVE 中成立。细步（0.25s）能修复，但醒来数翻 4 倍。
2. **长暂停**：30 秒停表演出期间，固定步仍逐格醒来（40/160 次），
   事件跳非 LIVE 无线程、零醒来，恢复后从冻结值精确续走。
3. **多项期限重合**：同一墙钟点的犯规/罚球/超次/进球，两驱动产出完全
   相同的规范折叠顺序（`deadline_order` 样本），因为排序由 `TYPE_RANK`
   决定，与推进方式无关；超次罚球在两个驱动上都被拒。

## 4. 选择：事件跳（EventJumpDriver / EventJumpScheduler）

理由：在本赛事的真实负载（节内稀疏事件 + 长暂停/犯规停表 + 末秒压哨）下，
事件跳同时给出零量化误差和数量级更低的空闲开销，且不引入步长调参负担。
生产入口 `sport/server.py` 默认 `clock=event_jump`，并保留
`--clock fixed_poll` 一键回退到旧 50ms 轮询，旧客户端接口（`/state`、
`/cmd/*`、`/audit/*`、`/config`）完全不变，新增 `/driver` 仅暴露度量。

## 5. 反例：选定方案在哪些负载下不适用

1. **高频中断风暴**（`dense_interrupts`，每 0.2s 一次暂停/恢复）：
   期限密度超过粗固定步的网格密度时，事件跳醒来 41 次反超固定步 22 次，
   且每次跳跃都要重算下一内部期限。此负载下应选固定轮询或合并中断。
2. **零时长回合风暴**（`zero_duration_turn`）：同一墙钟点连续终结多个
   回合时，两个驱动都无法靠时间戳区分顺序，只能依赖 `seq` 平局裁决。
   事件跳的“按需醒来”退化为同刻批量折叠；若上游不能保证单调 `seq`，
   两种方案都会产生不确定球权——这是内核承诺模型的边界，不是时钟选型能解决的。
3. **只有周期采样能力的运行环境**：某些嵌入式/外部硬件只提供固定频率
   心跳、无法在任意时刻调度唤醒，事件跳无法落地，必须用固定步。
4. **亚步级暂停/恢复**：固定步在该场景有量化误差（1.0s 步 0.4s、
   0.25s 步 0.15s），事件跳为 0；反过来若业务能接受整秒粒度且依赖
   固定节拍做下游同步，固定步的确定性网格反而更易对接。

## 6. 旧接口兼容与回退

- `GameServer(cfg, clock="event_jump"|"fixed_poll")`，命令路径、状态
  快照、审计接口签名均未改；`http_smoke` 在两种调度下打完同一套
  常规赛+加时命令并断言结果一致。
- 回退：`python -m sport.server --clock fixed_poll`，行为与改造前的
  50ms 轮询等价（`FixedPollScheduler`）。

## 7. 界面如何启动（回合赛制内核已接入操作界面）

```
python -m sport.server --host 127.0.0.1 --port 8077 --clock event_jump
# 浏览器打开 http://127.0.0.1:8077/
```

- 控件可用性唯一来自 `/state` 的 `phase/possession/turn_id/active_fouls`
  （`applyControls`），不是前端本地状态：未开局、停表、无活动犯规、
  非节间等情况下对应按钮禁用。
- 提交得分/暂停后，“回合赛制内核状态”面板显式对照球权转换
  （如 `A → B`）、回合推进（`T0 → T1`）与真实赛钟前后值，停表区间标注
  “不耗赛钟”；`sport/ui_check.py` 对这一对照做了自动化核验。
- 被规则层拒绝的动作（无球权出手、停表出手、超次罚球等）弹出失败横幅，
  修订号、比分、回合、赛钟均不变，随后端 refresh 回滚控件——失败反馈
  回到回合赛制内核，而不是仅在脚本里打印。
- 仅有脚本不算完成：内核通过 HTTP 命令驱动真实 DOM 控件，页面顶栏芯片
  实时显示调度方案与 tick/醒来数。无浏览器环境下用
  `python -m sport.ui_check`（需先启动服务器）复现同一命令序列。

## 8. 文件索引

| 文件 | 作用 |
|---|---|
| `sport/drivers/base.py` | 驱动统一接口、意图序列、度量采集 |
| `sport/drivers/fixed_step.py` | 固定逻辑步原型 |
| `sport/drivers/event_jump.py` | 事件跳原型（离线确定性版） |
| `sport/drivers/scenarios.py` | 两驱动共用的 7 个事件场景与统一约定 |
| `sport/drivers/benchmark.py` | 可复跑对照实验，生成 measurements/ |
| `sport/drivers/tests.py` | 43 项驱动对照断言（含两个反例） |
| `sport/scheduler.py` | 生产调度器：EventJumpScheduler / FixedPollScheduler |
| `sport/server.py` | 比赛入口，默认事件跳，`--clock` 可回退 |
| `sport/http_smoke.py` | 两调度方案常规赛+加时端到端证据 |
| `sport/ui_check.py` | 界面球权/赛钟对照与失败反馈核验 |
| `sport/measurements/` | 原始测量数据、汇总、迁移追踪 |
