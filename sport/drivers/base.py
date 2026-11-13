"""驱动公共类型：意图序列、驱动接口与度量。

意图（Intent）是与推进方式无关的输入：在某个墙钟时刻 wall_at，对规则内核
调用某个命令。两个驱动按各自的时间推进策略在正确的墙钟点取出并执行意图，
承诺时刻 commit_at 不由意图提供，而由内核在执行瞬间从赛钟读取，保证两套
原型遵守同一份得分承诺约定。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from ..engine import RuleEngine
from ..models import Decision, Team


@dataclass
class Intent:
    """一条与驱动无关的比赛输入意图。

    label 仅用于报告；cmd 是 RuleEngine 上的无参可调用（由 scenarios 工厂
    按 team/points 等参数闭包生成），这样驱动不需要知道命令差异。
    """
    wall_at: float
    label: str
    cmd: Callable[[RuleEngine], Decision]
    # 参考承诺时刻：由场景按“精确时间轴”预算，用于量化精度误差，
    # 不参与内核裁决（内核只信自己的赛钟）。
    ref_commit_at: Optional[float] = None
    expect_accepted: Optional[bool] = None


@dataclass
class IntentFeed:
    """同一份事件源：两个驱动必须消费完全相同的意图序列。"""
    name: str
    intents: list[Intent]
    horizon: float                       # 推进到该墙钟时刻后结束
    config_overrides: dict[str, Any] = field(default_factory=dict)
    description: str = ""

    def copy(self) -> "IntentFeed":
        return IntentFeed(
            name=self.name, intents=list(self.intents), horizon=self.horizon,
            config_overrides=dict(self.config_overrides), description=self.description,
        )


@dataclass
class DriverMetrics:
    """一次驱动运行的原始度量。

    wakeups: 驱动醒来的总次数（含空闲醒来）；
    idle_wakeups: 醒来但没有任何意图可执行的次数；
    ticks: 送入规则内核 tick() 的次数；
    commands: 实际执行的命令意图数；
    accepted / rejected: 裁决计数；
    max_commit_error: 实际 commit_at 与参考承诺时刻的最大绝对偏差（秒）；
    deadline_order: 同一墙钟时刻折叠多个期限时的实际裁决类型顺序样本。
    """
    driver: str
    scenario: str
    step: Optional[float]
    wakeups: int = 0
    idle_wakeups: int = 0
    ticks: int = 0
    commands: int = 0
    accepted: int = 0
    rejected: int = 0
    max_commit_error: float = 0.0
    commit_errors: list[dict] = field(default_factory=list)
    verdicts: list[dict] = field(default_factory=list)
    deadline_order: list[dict] = field(default_factory=list)
    final_snapshot: dict = field(default_factory=dict)
    decisions: list[dict] = field(default_factory=list)
    clock_ledger: list[dict] = field(default_factory=list)
    wall_span: float = 0.0

    def to_row(self) -> dict:
        return {
            "driver": self.driver,
            "scenario": self.scenario,
            "step": self.step,
            "wakeups": self.wakeups,
            "idle_wakeups": self.idle_wakeups,
            "ticks": self.ticks,
            "commands": self.commands,
            "accepted": self.accepted,
            "rejected": self.rejected,
            "max_commit_error": round(self.max_commit_error, 6),
            "wall_span": round(self.wall_span, 6),
        }


class ClockDriver:
    """时钟推进驱动的统一接口，两套实现都可直接接入规则服务。"""

    name = "base"

    def __init__(self, engine: RuleEngine) -> None:
        self.engine = engine
        self.wakeups = 0
        self.idle_wakeups = 0
        self.ticks = 0

    # 子类实现：把赛钟从当前墙钟推进到 wall_now
    def advance_to(self, wall_now: float) -> None:
        raise NotImplementedError

    def _cap_target(self, target: float) -> float:
        """事件跳驱动重写：若赛钟零点早于下一意图，先在零点醒来一次。

        固定步驱动不需要拦截——逐格推进时零点会在某个步边界自然命中。
        """
        return target

    # 子类实现：是否还有未处理的内部期限（事件跳用）
    def pending_deadlines(self) -> int:
        return 0

    def run_feed(self, feed: IntentFeed) -> DriverMetrics:
        """消费一份意图序列，返回原始度量；两个驱动的执行骨架完全一致。"""
        metrics = DriverMetrics(
            driver=self.name, scenario=feed.name,
            step=getattr(self, "step", None),
        )
        eng = self.engine
        # 意图按墙钟时刻排序；同刻意图按入列顺序（场景负责给出确定顺序）
        ordered = sorted(feed.intents, key=lambda i: (i.wall_at, i.label))
        cursor = 0
        while cursor < len(ordered):
            target = ordered[cursor].wall_at
            target = self._cap_target(target)
            before_wakeups = self.wakeups
            self.advance_to(target)
            due = [i for i in ordered[cursor:] if i.wall_at <= target + 1e-12]
            if not due:
                # 这次醒来只服务内部期限（如赛钟零点鸣笛），没有外部意图
                self.idle_wakeups += 1
            for intent in due:
                before = eng.snapshot()
                d = intent.cmd(eng)
                metrics.commands += 1
                if d.accepted:
                    metrics.accepted += 1
                else:
                    metrics.rejected += 1
                metrics.verdicts.append({
                    "label": intent.label,
                    "accepted": d.accepted,
                    "reason": d.reason,
                    "event_id": d.event_id,
                })
                self._record_commit_error(metrics, intent, before, d)
                cursor += 1
        self.advance_to(feed.horizon)
        metrics.wakeups = self.wakeups
        metrics.idle_wakeups = self.idle_wakeups
        metrics.ticks = self.ticks
        metrics.wall_span = feed.horizon
        metrics.final_snapshot = eng.snapshot()
        metrics.decisions = eng.audit_decisions()
        metrics.clock_ledger = eng.audit_clock()
        metrics.max_commit_error = max(
            (e["abs_error"] for e in metrics.commit_errors), default=0.0
        )
        metrics.deadline_order = self._deadline_order_samples(eng)
        return metrics

    def _record_commit_error(self, metrics: DriverMetrics, intent: Intent,
                             before: dict, d: Decision) -> None:
        if intent.ref_commit_at is None:
            return
        # 被拒绝的意图没有事件可查（量化误拒正是固定步的关键误差来源），
        # 用意图执行瞬间内核赛钟剩余值作为实际承诺点，同样计入误差。
        if not d.accepted or not d.event_id:
            actual = round(self.engine.clock.remaining, 4)
        else:
            ev_by_id = {e["id"]: e for e in self.engine.audit_events()}
            ev = ev_by_id.get(d.event_id)
            if ev is None:
                return
            actual = ev["commit_at"]
        err = abs(actual - intent.ref_commit_at)
        metrics.commit_errors.append({
            "label": intent.label,
            "event_id": d.event_id,
            "ref_commit_at": intent.ref_commit_at,
            "actual_commit_at": actual,
            "abs_error": round(err, 6),
            "accepted": d.accepted,
            "reason": d.reason,
        })

    def _deadline_order_samples(self, eng: RuleEngine) -> list[dict]:
        """找出同一承诺时刻折叠了多个事件的期限，记录规范裁决顺序。"""
        groups: dict[tuple[int, float], list[dict]] = {}
        for ev in eng.audit_events():
            if ev["voided"]:
                continue
            groups.setdefault((ev["period"], ev["commit_at"]), []).append(ev)
        samples = []
        for (period, commit_at), evs in groups.items():
            if len(evs) < 2:
                continue
            samples.append({
                "period": period,
                "commit_at": commit_at,
                "order": [e["type"] for e in evs],
                "seq_order": [e["seq"] for e in evs],
            })
        return sorted(samples, key=lambda s: (s["period"], -s["commit_at"]))
