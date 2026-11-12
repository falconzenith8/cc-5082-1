"""双时钟：墙钟（wall clock）与有效比赛时钟（game clock）。

墙钟单调向前，由服务端时间源驱动；有效时钟只在 LIVE 期间递减。
停表期间发生的演出（free_throw、timeout 等）不会消耗有效时间，也不消耗回合。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ClockLedger:
    """一次时钟迁移的审计记录。"""
    wall_at: float
    phase: str
    game_remaining_before: float
    game_remaining_after: float
    note: str

    def to_dict(self) -> dict:
        return {
            "wall_at": round(self.wall_at, 4),
            "phase": self.phase,
            "game_remaining_before": round(self.game_remaining_before, 4),
            "game_remaining_after": round(self.game_remaining_after, 4),
            "note": self.note,
        }


class GameClock:
    def __init__(self, initial_remaining: float, wall_now: float) -> None:
        self.remaining = initial_remaining
        self.live = False
        self.total_live_seconds = 0.0
        self.ledger: list[ClockLedger] = []
        self._last_wall = wall_now

    def _sync(self, wall_now: float, note: str = "tick") -> None:
        """按墙钟增量推进：只有 LIVE 期间的墙钟增量才扣有效时钟；
        停表期间无论墙钟走多久，有效时钟都不动。"""
        before = self.remaining
        if wall_now == self._last_wall:
            return
        delta = wall_now - self._last_wall
        if delta < 0:
            delta = 0.0
        if self.live and delta > 0.0:
            consumed = min(delta, self.remaining)
            self.remaining -= consumed
            self.total_live_seconds += consumed
            if self.remaining == 0.0 and before > 0.0:
                note = "buzzer_zero"
        self._last_wall = wall_now
        if abs(before - self.remaining) > 1e-9 or note not in ("tick",):
            self.ledger.append(
                ClockLedger(wall_now, "LIVE" if self.live else "STOPPED",
                            before, self.remaining, note)
            )

    def pause(self, wall_now: float, note: str) -> None:
        # 先按墙钟结清 LIVE 期间的消耗，再冻结；停表后 _sync 不再改动剩余值
        if self.live:
            self._sync(wall_now)
            self.live = False
            self.ledger.append(
                ClockLedger(wall_now, "STOPPED", self.remaining, self.remaining, note)
            )
        self._last_wall = wall_now

    def resume(self, wall_now: float, note: str) -> None:
        self._last_wall = wall_now
        if not self.live and self.remaining > 0.0:
            self.live = True
            self.ledger.append(
                ClockLedger(wall_now, "LIVE", self.remaining, self.remaining, note)
            )

    def reset(self, remaining: float, wall_now: float, note: str) -> None:
        before = self.remaining
        self.live = False
        self.remaining = remaining
        self._last_wall = wall_now
        self.ledger.append(ClockLedger(wall_now, "STOPPED", before, remaining, note))

    def reached_zero(self, wall_now: float) -> bool:
        """同步墙钟并报告本次是否跨越有效时钟零点；跨越时冻结 LIVE。"""
        was_live = self.live
        had_remaining = self.remaining > 0.0
        self._sync(wall_now)
        crossed = was_live and had_remaining and self.remaining <= 0.0
        if crossed:
            self.live = False
            self.ledger.append(
                ClockLedger(wall_now, "STOPPED", 0.0, 0.0, "buzzer_zero_freeze")
            )
        return crossed

    def snapshot(self, wall_now: float) -> dict:
        self._sync(wall_now)
        return {
            "remaining": round(self.remaining, 4),
            "live": self.live,
            "total_live_seconds": round(self.total_live_seconds, 4),
        }
