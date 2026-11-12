from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Optional


class Phase(str, Enum):
    IDLE = "IDLE"                       # 未开赛
    PREGAME = "PREGAME"                 # 已开局，第一节未开始
    LIVE = "LIVE"                       # 有效比赛时间流动
    PAUSED = "PAUSED"                   # 停表（暂停/犯规/官方暂停）
    INTERMISSION = "INTERMISSION"       # 节间，节结果尚未封印
    FINAL = "FINAL"                     # 终场


class Team(str, Enum):
    A = "A"
    B = "B"

    @property
    def other(self) -> "Team":
        return Team.B if self is Team.A else Team.A


class EType(str, Enum):
    START_MATCH = "start_match"
    START_PERIOD = "start_period"
    BUZZER = "buzzer"
    PAUSE = "pause"
    RESUME = "resume"
    TIMEOUT = "timeout"
    POSSESSION = "possession"
    GOAL = "goal"
    SHOT_MISS = "shot_miss"
    FOUL = "foul"
    FREE_THROW = "free_throw"


# 同一承诺时刻的规范排序优先级：鸣笛永远排在进球之后，
# 因此压哨球在折叠到该位置时比赛仍处于 LIVE，裁决只取决于承诺时刻。
TYPE_RANK = {
    EType.START_MATCH: 0,
    EType.POSSESSION: 1,
    EType.FOUL: 2,
    EType.TIMEOUT: 3,
    EType.PAUSE: 4,
    EType.RESUME: 5,
    EType.GOAL: 6,
    EType.SHOT_MISS: 7,
    EType.FREE_THROW: 8,
    EType.BUZZER: 9,
    EType.START_PERIOD: 10,
}


@dataclass
class MatchConfig:
    regulation_quarters: int = 4
    quarter_seconds: float = 60.0
    ot_seconds: float = 30.0
    timeouts_reg: int = 3
    timeouts_ot: int = 1
    goal_points: int = 2
    ft_points: int = 1
    ft_attempts: int = 2

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GameEvent:
    """带承诺时刻的比赛事件。commit_at = 承诺瞬间的有效比赛剩余秒数。"""
    id: str
    type: EType
    team: Optional[Team]
    period: int
    turn_id: int
    commit_at: float
    wall_at: float
    seq: int
    payload: dict[str, Any] = field(default_factory=dict)
    voided: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "team": self.team.value if self.team else None,
            "period": self.period,
            "turn_id": self.turn_id,
            "commit_at": round(self.commit_at, 4),
            "wall_at": round(self.wall_at, 4),
            "seq": self.seq,
            "payload": self.payload,
            "voided": self.voided,
        }


@dataclass
class Decision:
    """规则层对一次输入的裁决，形成可审计链。"""
    seq: int
    accepted: bool
    reason: str
    revision_after: int
    event_id: Optional[str] = None
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Revocation:
    target_id: str
    wall_at: float
    reason: str
    cascaded: list[str] = field(default_factory=list)
