"""按事件跳到下一期限的推进：无轮询，只在“下一期限”醒来。

期限只有两类：
1. 外部意图声明的墙钟时刻（Intent.wall_at）；
2. 赛钟自然零点——仅当赛钟 LIVE 时存在，等于
   当前墙钟 + 当前赛钟剩余秒。

非 LIVE（暂停/节间/未开赛）期间不存在内部期限，驱动直接睡到下一意图，
长暂停产生零次空闲醒来、零次 tick。同一墙钟时刻重合的多个期限在一次醒来中
全部折叠，裁决顺序交给规则内核的规范排序 (commit_at, TYPE_RANK, seq)。
"""
from __future__ import annotations

from ..engine import RuleEngine
from ..models import Phase
from .base import ClockDriver


class EventJumpDriver(ClockDriver):
    name = "event_jump"

    def __init__(self, engine: RuleEngine) -> None:
        super().__init__(engine)
        self._cursor: float | None = None

    def advance_to(self, wall_now: float) -> None:
        if self._cursor is None:
            self._cursor = wall_now
            # 首次对齐只建立基线，不产生醒来/tick
            self.engine.tick(wall_now)
            return
        if wall_now < self._cursor - 1e-12:
            raise ValueError("事件跳驱动只支持单调向前的墙钟")
        # 一次跳跃直达期限：中间没有任何醒来
        self.wakeups += 1
        self.engine.tick(wall_now)
        self.ticks += 1
        self._cursor = wall_now

    def _cap_target(self, target: float) -> float:
        deadline = self.next_internal_deadline()
        if deadline is not None and deadline < target - 1e-12:
            return deadline
        return target

    def next_internal_deadline(self) -> float | None:
        """赛钟零点期限；非 LIVE 时返回 None（无内部期限可跳）。"""
        st = self.engine.fold()
        if st.phase is not Phase.LIVE:
            return None
        remaining = self.engine.clock.remaining
        if remaining <= 0.0:
            return None
        base = self._cursor if self._cursor is not None else self.engine._wall
        return base + remaining

    def pending_deadlines(self) -> int:
        return 1 if self.next_internal_deadline() is not None else 0
