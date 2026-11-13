"""固定逻辑步推进：时间轴量化为 step，每个步边界固定醒来一次。

这是轮询式实现的原型化版本：无论下一个期限何时到来，驱动都以固定步长
推进，步内发生的意图只能在下一个步边界被处理，因此承诺时刻被量化到步网格，
且每次醒来都计入空闲开销。step 越小精度越高、空闲开销越大。
"""
from __future__ import annotations

from ..engine import RuleEngine
from .base import ClockDriver


class FixedStepDriver(ClockDriver):
    name = "fixed_step"

    def __init__(self, engine: RuleEngine, step: float = 1.0,
                 wall_start: float = 0.0) -> None:
        super().__init__(engine)
        if step <= 0:
            raise ValueError("step 必须为正秒数")
        self.step = float(step)
        # 网格原点：首个步边界为 wall_start + step，引擎从该墙钟时刻起被驱动。
        self._cursor: float = float(wall_start)

    def advance_to(self, wall_now: float) -> None:
        # 固定步会越过意图时刻（量化到下一个步边界）；当后续意图落在已跨过
        # 的网格内时，目标时刻早于游标是正常现象，此时无需推进，意图在当前
        # 已到达的墙钟点就地处理（其承诺时刻同样被量化到该网格点）。
        if wall_now <= self._cursor + 1e-12:
            return
        # 逐格跳到第一个覆盖 wall_now 的步边界；每一格都是一次真实醒来。
        # 不向 wall_now 吸附：吸附会少算步数，破坏固定步语义。
        while self._cursor < wall_now - 1e-12:
            self._cursor += self.step
            self.wakeups += 1
            self.engine.tick(self._cursor)
            self.ticks += 1

    def pending_deadlines(self) -> int:
        return 0
