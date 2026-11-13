"""两套比赛时钟推进原型：固定逻辑步 vs 按事件跳到下一期限。

两个驱动消费同一份意图序列（IntentFeed），复用同一个规则内核 RuleEngine，
因此裁决规则只有一份实现；差异只来自“时间如何推进”：

- FixedStepDriver：把时间轴量化为固定逻辑步 step，每个步边界醒来一次，
  无论有无事件都要付出一次 tick（空闲开销与赛事长度成正比）。
- EventJumpDriver：不轮询，只在下一期限（下一个承诺时刻或时钟零点）醒来，
  空闲开销只与实际期限数相关。

统一约定（见 sport/drivers/scenarios.py 的 UNIT_NOTES）：
- 时间单位统一为“有效比赛秒”（浮点秒），墙钟与赛钟同单位；
- 得分承诺统一为 commit_at = 承诺瞬间的赛钟剩余秒（倒计时），
  事件排序键 (period, 节长-commit_at, TYPE_RANK, seq) 两个驱动完全相同。
"""
from .base import ClockDriver, DriverMetrics, Intent, IntentFeed
from .fixed_step import FixedStepDriver
from .event_jump import EventJumpDriver

__all__ = [
    "ClockDriver", "DriverMetrics", "Intent", "IntentFeed",
    "FixedStepDriver", "EventJumpDriver",
]
