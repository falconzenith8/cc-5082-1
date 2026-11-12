"""Circuit Ball 规则内核。

设计要点：
- 事件溯源：所有被接受的输入都成为带承诺时刻 (commit_at) 的不可变事件；
  比分/球权/阶段/暂停预算全部由事件流折叠得出，不存在手工改分。
- 承诺时刻裁决：事件按 (period, commit_at, 类型优先级, seq) 规范排序，
  鸣笛 BUZZER 的类型优先级低于进球，压哨球即使晚到也在鸣笛前折叠，
  裁决不依赖网络回调先后。
- 迟到旧回合事件：新节开始即封印上一节，旧事件被拒绝，不能改动新比分。
- 撤销：void 对应事件并重新折叠；犯规撤销级联作废其罚球；
  若后续事件依赖被撤销事件的效果（同一回合已有后续动作），拒绝撤销。
"""
from __future__ import annotations

import itertools
import uuid
from dataclasses import dataclass, field
from typing import Optional

from .clock import GameClock
from .models import (
    Decision, EType, GameEvent, MatchConfig, Phase, Revocation, Team, TYPE_RANK,
)


class RuleError(Exception):
    pass


REVOCABLE = {
    EType.GOAL, EType.SHOT_MISS, EType.FOUL,
    EType.TIMEOUT, EType.FREE_THROW, EType.POSSESSION,
}


@dataclass
class FoldState:
    phase: Phase = Phase.IDLE
    period: int = 0
    turn: int = 0
    possession: Optional[Team] = None
    scores: dict[Team, int] = field(default_factory=lambda: {Team.A: 0, Team.B: 0})
    period_scores: dict[int, dict[Team, int]] = field(default_factory=dict)
    timeout_used: dict[tuple[int, Team], int] = field(default_factory=dict)
    active_fouls: dict[str, dict] = field(default_factory=dict)
    # turn 上已经出现的事件类型，用于球权/回合依赖校验
    turn_events: dict[tuple[int, int], list[EType]] = field(default_factory=dict)
    # 每回合实际持球方，校验目标球权
    turn_possession: dict[tuple[int, int], Team] = field(default_factory=dict)
    buzzer_seen: set[int] = field(default_factory=set)
    started_periods: set[int] = field(default_factory=set)
    last_event: Optional[GameEvent] = None


def _period_budget(cfg: MatchConfig, period: int) -> int:
    return cfg.timeouts_reg if period <= cfg.regulation_quarters else cfg.timeouts_ot


class RuleEngine:
    def __init__(self, cfg: Optional[MatchConfig] = None, wall_now: float = 0.0) -> None:
        self.cfg = cfg or MatchConfig()
        self._wall = wall_now
        self._seq = itertools.count(1)
        self.events: list[GameEvent] = []
        self.decisions: list[Decision] = []
        self.revocations: list[Revocation] = []
        self.revision = 0
        self.clock = GameClock(self.cfg.quarter_seconds, wall_now)
        self._voided: set[str] = set()

    # ---------- 时间源 ----------
    def tick(self, wall_now: float) -> None:
        """服务端墙钟驱动；有效时钟归零时自动产生鸣笛事件（只产生一次）。"""
        self._wall = wall_now
        state = self.fold()
        if state.phase is not Phase.LIVE:
            # 仍需同步墙钟基线，停表区间的增量不得在恢复后被追算
            self.clock.reached_zero(wall_now)
            return
        before_period = state.period
        crossed = self.clock.reached_zero(wall_now)
        if crossed:
            self._append_buzzer(wall_now, period=before_period)

    # ---------- 折叠 ----------
    def fold(self) -> FoldState:
        st = FoldState()
        foul_fts: dict[str, list[str]] = {}
        for ev in self._sorted_events():
            if ev.id in self._voided:
                continue  # 作废事件（含级联罚球）不参与折叠
            self._apply(st, ev, foul_fts)
        return st

    def _period_length(self, period: int) -> float:
        return (self.cfg.ot_seconds if period > self.cfg.regulation_quarters
                else self.cfg.quarter_seconds)

    def _order_key(self, e: GameEvent):
        # commit_at 是承诺瞬间的“剩余秒数”（倒计时），时间轴坐标要换算成
        # 已消耗时间 = 节长度 - commit_at；剩余越小，发生越晚。
        if e.type is EType.START_MATCH:
            return (0, 0, -1.0, TYPE_RANK[e.type], e.seq)
        if e.type is EType.START_PERIOD:
            return (1, e.period, -1.0, TYPE_RANK[e.type], e.seq)
        elapsed = self._period_length(e.period) - e.commit_at
        return (1, e.period, elapsed, TYPE_RANK[e.type], e.seq)

    def _sorted_events(self) -> list[GameEvent]:
        # 每节的 START_PERIOD 是该节时间线的起点，必须排在该节所有事件之前；
        # 节内再按承诺时刻（换算为已消耗时间）、类型优先级、序列号规范排序。
        return sorted(self.events, key=self._order_key)

    def _ordered_with(self, extra: GameEvent) -> list[GameEvent]:
        return sorted(self.events + [extra], key=self._order_key)

    def _apply(self, st: FoldState, ev: GameEvent, foul_fts: dict) -> None:
        t = ev.type
        if t is EType.START_MATCH:
            st.phase = Phase.PREGAME
            st.period = 0
        elif t is EType.START_PERIOD:
            st.phase = Phase.LIVE
            st.period = ev.period
            st.turn = 0
            st.possession = Team(ev.payload["first_possession"])
            st.started_periods.add(ev.period)
            st.period_scores.setdefault(ev.period, {Team.A: 0, Team.B: 0})
        elif t is EType.BUZZER:
            st.phase = Phase.INTERMISSION
            st.buzzer_seen.add(ev.period)
        elif t is EType.PAUSE:
            st.phase = Phase.PAUSED
        elif t is EType.RESUME:
            st.phase = Phase.LIVE
        elif t is EType.POSSESSION:
            st.possession = Team(ev.team)
            st.turn = ev.turn_id
            st.turn_events.setdefault((ev.period, ev.turn_id), []).append(t)
            st.turn_possession[(ev.period, ev.turn_id)] = Team(ev.team)
        elif t is EType.TIMEOUT:
            key = (ev.period, Team(ev.team))
            st.timeout_used[key] = st.timeout_used.get(key, 0) + 1
            st.phase = Phase.PAUSED
            st.turn_events.setdefault((ev.period, ev.turn_id), []).append(t)
        elif t is EType.GOAL:
            pts = ev.payload.get("points", self.cfg.goal_points)
            st.scores[Team(ev.team)] += pts
            st.period_scores.setdefault(ev.period, {Team.A: 0, Team.B: 0})
            st.period_scores[ev.period][Team(ev.team)] += pts
            # 进球后球权自然转换，进入下一回合
            st.possession = Team(ev.team).other
            st.turn = ev.turn_id + 1
            st.turn_events.setdefault((ev.period, ev.turn_id), []).append(t)
            st.turn_possession.setdefault((ev.period, ev.turn_id), Team(ev.team))
        elif t is EType.SHOT_MISS:
            st.possession = Team(ev.team).other
            st.turn = ev.turn_id + 1
            st.turn_events.setdefault((ev.period, ev.turn_id), []).append(t)
            st.turn_possession.setdefault((ev.period, ev.turn_id), Team(ev.team))
        elif t is EType.FOUL:
            st.active_fouls[ev.id] = {
                "team": ev.team, "period": ev.period, "turn_id": ev.turn_id,
                "free_throws": [],
            }
            st.phase = Phase.PAUSED
            st.turn_events.setdefault((ev.period, ev.turn_id), []).append(t)
            st.turn_possession.setdefault((ev.period, ev.turn_id), Team(ev.team))
        elif t is EType.FREE_THROW:
            foul_id = ev.payload["foul_id"]
            if ev.payload.get("made"):
                st.scores[Team(ev.team)] += self.cfg.ft_points
                st.period_scores.setdefault(ev.period, {Team.A: 0, Team.B: 0})
                st.period_scores[ev.period][Team(ev.team)] += self.cfg.ft_points
            st.active_fouls.setdefault(foul_id, {"free_throws": []})
            st.active_fouls[foul_id].setdefault("free_throws", []).append(ev.id)
            foul_fts.setdefault(foul_id, []).append(ev.id)
        st.last_event = ev

    # ---------- 内部工具 ----------
    def _next_id(self) -> str:
        return f"ev{next(self._seq)}-{uuid.uuid4().hex[:8]}"

    def _current_commit_at(self) -> float:
        return round(self.clock.remaining, 4)

    def _reject(self, reason: str, **detail) -> Decision:
        d = Decision(next(self._seq), False, reason, self.revision, detail=detail)
        self.decisions.append(d)
        return d

    def _accept(self, ev: GameEvent, reason: str = "accepted") -> Decision:
        self.events.append(ev)
        self.revision += 1
        d = Decision(ev.seq, True, reason, self.revision, ev.id)
        self.decisions.append(d)
        return d

    def _append_buzzer(self, wall_now: float, period: Optional[int] = None) -> None:
        st = self.fold()
        period = period or st.period
        if period in st.buzzer_seen or period == 0:
            return
        ev = GameEvent(
            id=self._next_id(), type=EType.BUZZER, team=None, period=period,
            turn_id=st.turn, commit_at=0.0, wall_at=wall_now,
            seq=next(self._seq), payload={"auto": True},
        )
        self._accept(ev, "buzzer_auto")

    def _validate_insert(self, ev: GameEvent) -> tuple[bool, str, FoldState]:
        """把候选事件插入规范位置后重放，验证全部规则不变量。"""
        if ev.commit_at < -1e-9:
            return False, "commit_at_negative", self.fold()
        # 封印检查基于当前已接受的事件流：候选无论按承诺时刻排在哪里，
        # 只要更新的节已经开始，旧节事件就不能再进入时间线。
        current = self.fold()
        if ev.period and any(p > ev.period for p in current.started_periods):
            return False, "period_sealed_late_event", current
        st = FoldState()
        foul_fts: dict[str, list[str]] = {}
        candidate_passed = False
        ordered = self._ordered_with(ev)
        for cur in ordered:
            active = cur.id not in self._voided
            if not active:
                continue
            ok, reason = self._check_invariants(st, cur, cur is ev)
            if not ok:
                return False, reason, st
            self._apply(st, cur, foul_fts)
            if cur is ev:
                candidate_passed = True
        if not candidate_passed:
            return False, "candidate_voided", st
        return True, "ok", st

    def _check_invariants(self, st: FoldState, ev: GameEvent, is_candidate: bool):
        t = ev.type
        # 节封印：已开始更新的节后，旧节事件一律拒绝（优先级最高，
        # 保证迟到旧回合事件无论承诺时刻都不能改动已封印节的比分）
        if ev.period and any(p > ev.period for p in st.started_periods):
            return False, "period_sealed_late_event"
        if t is EType.START_MATCH:
            if st.phase is not Phase.IDLE:
                return False, "illegal_restart"
            return True, ""
        if t is EType.START_PERIOD:
            if st.phase not in (Phase.PREGAME, Phase.INTERMISSION):
                return False, "start_period_wrong_phase"
            expected = st.period + 1 if st.phase is Phase.INTERMISSION else 1
            if ev.period != expected:
                return False, "period_number_mismatch"
            if ev.period > self.cfg.regulation_quarters:
                # 加时资格按累计总比分裁决
                if st.scores[Team.A] != st.scores[Team.B]:
                    return False, "ot_requires_tied_regulation"
            return True, ""
        if t is EType.BUZZER:
            if st.phase is not Phase.LIVE:
                return False, "buzzer_wrong_phase"
            if ev.period != st.period:
                return False, "buzzer_period_mismatch"
            return True, ""
        if t is EType.PAUSE:
            if st.phase not in (Phase.LIVE, Phase.PAUSED):
                return False, "pause_wrong_phase"
            return True, ""
        if t is EType.RESUME:
            if st.phase not in (Phase.PAUSED,):
                return False, "resume_wrong_phase"
            return True, ""
        # 以下为节内比赛事件
        if st.phase not in (Phase.LIVE, Phase.PAUSED, Phase.INTERMISSION):
            return False, f"{t.value}_wrong_phase"
        if st.phase is Phase.INTERMISSION and ev.period != st.period:
            return False, "late_event_wrong_period"
        # 鸣笛后的迟到事件：只有 commit_at == 0 的压哨承诺才合法。
        # 先于 turn/球权校验，使裁决理由精确反映“承诺晚于鸣笛”。
        if ev.period in st.buzzer_seen and ev.commit_at > 1e-9:
            return False, "committed_after_buzzer"
        if t is EType.TIMEOUT:
            budget = _period_budget(self.cfg, ev.period)
            used = st.timeout_used.get((ev.period, Team(ev.team)), 0)
            if used >= budget:
                return False, "timeout_budget_exhausted"
            if st.phase is Phase.INTERMISSION:
                return False, "timeout_in_intermission"
            return True, ""
        if t is EType.POSSESSION:
            if st.phase is not Phase.LIVE:
                return False, "possession_requires_live"
            if ev.turn_id != st.turn:
                return False, "stale_turn_id"
            types = st.turn_events.get((ev.period, ev.turn_id), [])
            if EType.GOAL in types or EType.SHOT_MISS in types:
                return False, "turn_already_resolved"
            return True, ""
        if t in (EType.GOAL, EType.SHOT_MISS):
            if st.phase is not Phase.LIVE:
                # 节间只接受鸣笛同刻（commit_at==0）的压哨承诺，
                # 其 turn 必须等于鸣笛时冻结的回合
                if not (st.phase is Phase.INTERMISSION
                        and ev.period in st.buzzer_seen
                        and abs(ev.commit_at) <= 1e-9
                        and ev.turn_id == st.turn):
                    return False, "shot_requires_live"
            elif ev.turn_id != st.turn:
                return False, "stale_turn_id"
            if st.possession is not None and st.possession != Team(ev.team):
                return False, "team_without_possession"
            types = st.turn_events.get((ev.period, ev.turn_id), [])
            if EType.GOAL in types or EType.SHOT_MISS in types:
                return False, "duplicate_shot_same_turn"
            return True, ""
        if t is EType.FOUL:
            if ev.turn_id != st.turn:
                return False, "stale_turn_id"
            if st.phase is Phase.INTERMISSION:
                return False, "foul_in_intermission"
            return True, ""
        if t is EType.FREE_THROW:
            foul_id = ev.payload.get("foul_id")
            foul = st.active_fouls.get(foul_id)
            if foul is None:
                return False, "free_throw_without_active_foul"
            if foul["team"] == ev.team:
                return False, "free_throw_team_mismatch"
            if len(foul.get("free_throws", [])) >= self.cfg.ft_attempts:
                return False, "free_throw_attempts_exceeded"
            return True, ""
        return False, "unknown_event_type"

    def _ingest(self, etype: EType, team: Optional[Team], period: int,
                turn_id: int, commit_at: float, payload: dict) -> Decision:
        ev = GameEvent(
            id=self._next_id(), type=etype, team=team, period=period,
            turn_id=turn_id, commit_at=round(commit_at, 4),
            wall_at=self._wall, seq=next(self._seq), payload=payload,
        )
        ok, reason, _ = self._validate_insert(ev)
        if not ok:
            return self._reject(reason, event_type=etype.value)
        return self._accept(ev)

    # ---------- 公共命令 ----------
    def start_match(self, first_possession: Team = Team.A) -> Decision:
        st = self.fold()
        if st.phase is not Phase.IDLE:
            return self._reject("illegal_restart")
        ev = GameEvent(
            id=self._next_id(), type=EType.START_MATCH, team=None, period=0,
            turn_id=0, commit_at=0.0, wall_at=self._wall, seq=next(self._seq),
        )
        return self._accept(ev, "match_started")

    def start_period(self, first_possession: Team) -> Decision:
        st = self.fold()
        if st.phase is Phase.IDLE:
            return self._reject("match_not_started")
        if st.phase is Phase.FINAL:
            return self._reject("match_final")
        if st.phase is Phase.LIVE:
            return self._reject("period_already_live")
        if st.phase is Phase.PAUSED:
            return self._reject("resume_required")
        period = (st.period + 1) if st.phase is Phase.INTERMISSION else 1
        if period > self.cfg.regulation_quarters:
            st_now = self.fold()
            if st_now.scores[Team.A] != st_now.scores[Team.B]:
                return self._reject("ot_requires_tied_regulation")
        length = (self.cfg.ot_seconds if period > self.cfg.regulation_quarters
                  else self.cfg.quarter_seconds)
        ev = GameEvent(
            id=self._next_id(), type=EType.START_PERIOD, team=None,
            period=period, turn_id=0, commit_at=length, wall_at=self._wall,
            seq=next(self._seq),
            payload={"first_possession": first_possession.value},
        )
        ok, reason, _ = self._validate_insert(ev)
        if not ok:
            return self._reject(reason)
        d = self._accept(ev)
        self.clock.reset(length, self._wall, f"period_{period}_reset")
        self.clock.resume(self._wall, f"period_{period}_live")
        return d

    def pause(self, note: str = "official_pause") -> Decision:
        st = self.fold()
        if st.phase not in (Phase.LIVE, Phase.PAUSED):
            return self._reject("pause_wrong_phase")
        d = self._ingest(EType.PAUSE, None, st.period, st.turn,
                         self._current_commit_at(), {"note": note})
        if d.accepted:
            self.clock.pause(self._wall, note)
        return d

    def resume(self) -> Decision:
        st = self.fold()
        if st.phase is not Phase.PAUSED:
            return self._reject("resume_wrong_phase")
        d = self._ingest(EType.RESUME, None, st.period, st.turn,
                         self._current_commit_at(), {})
        if d.accepted:
            self.clock.resume(self._wall, "resume")
        return d

    def timeout(self, team: Team) -> Decision:
        st = self.fold()
        if st.phase is Phase.INTERMISSION:
            return self._reject("timeout_in_intermission")
        if st.phase not in (Phase.LIVE, Phase.PAUSED):
            return self._reject("timeout_wrong_phase")
        d = self._ingest(EType.TIMEOUT, team, st.period, st.turn,
                         self._current_commit_at(), {})
        if d.accepted:
            self.clock.pause(self._wall, f"timeout_{team.value}")
        return d

    def possession(self, team: Team) -> Decision:
        st = self.fold()
        if st.phase is not Phase.LIVE:
            return self._reject("possession_requires_live")
        return self._ingest(EType.POSSESSION, team, st.period, st.turn,
                            self._current_commit_at(), {})

    def goal(self, team: Team, points: Optional[int] = None) -> Decision:
        st = self.fold()
        if st.phase is not Phase.LIVE:
            return self._reject("shot_requires_live")
        pts = points if points is not None else self.cfg.goal_points
        return self._ingest(EType.GOAL, team, st.period, st.turn,
                            self._current_commit_at(), {"points": pts})

    def shot_miss(self, team: Team) -> Decision:
        st = self.fold()
        if st.phase is not Phase.LIVE:
            return self._reject("shot_requires_live")
        return self._ingest(EType.SHOT_MISS, team, st.period, st.turn,
                            self._current_commit_at(), {})

    def foul(self, team: Team) -> Decision:
        st = self.fold()
        if st.phase not in (Phase.LIVE, Phase.PAUSED):
            return self._reject("foul_wrong_phase")
        d = self._ingest(EType.FOUL, team, st.period, st.turn,
                         self._current_commit_at(), {})
        if d.accepted:
            self.clock.pause(self._wall, f"foul_{team.value}")
        return d

    def free_throw(self, team: Team, foul_id: str, made: bool) -> Decision:
        st = self.fold()
        foul = st.active_fouls.get(foul_id)
        if foul is None:
            return self._reject("free_throw_without_active_foul")
        return self._ingest(EType.FREE_THROW, team, foul["period"],
                            foul["turn_id"], self._current_commit_at(),
                            {"foul_id": foul_id, "made": made})

    def revoke(self, target_id: str, reason: str = "review_override") -> Decision:
        st = self.fold()
        target = next((e for e in self.events if e.id == target_id), None)
        if target is None:
            return self._reject("event_not_found")
        if target_id in self._voided:
            return self._reject("already_voided")
        if target.type not in REVOCABLE:
            return self._reject("not_revocable")
        # 依赖检查：被撤事件之后若已出现终结回合的投篮，回合链已向前推进，
        # 撤销会破坏后续球权/比分 -> 拒绝；鸣笛/暂停/罚球/犯规等附属事件不阻塞，
        # 因此压哨球可在节间复审撤销，犯规可连同罚球一起级联回退。
        blocking = {EType.GOAL, EType.SHOT_MISS}
        later_terminal = [
            e for e in self.events
            if e.id not in self._voided and e.seq > target.seq and e.type in blocking
        ]
        if later_terminal:
            return self._reject("dependent_events_exist",
                                blockers=[e.id for e in later_terminal])
        cascaded: list[str] = []
        if target.type is EType.FOUL:
            cascaded = [
                e.id for e in self.events
                if e.type is EType.FREE_THROW
                and e.payload.get("foul_id") == target_id
                and e.id not in self._voided
            ]
        self._voided.add(target_id)
        self._voided.update(cascaded)
        # 若被撤事件是停表来源（犯规/暂停），撤销后折叠阶段回到 LIVE，
        # 物理时钟需同步恢复；若仍有其他停表事件则保持冻结。
        if target.type in (EType.FOUL, EType.TIMEOUT):
            new_state = self.fold()
            if new_state.phase is Phase.LIVE and not self.clock.live:
                self.clock.resume(self._wall, "revoke_restores_live")
        self.revocations.append(
            Revocation(target_id, self._wall, reason, cascaded)
        )
        self.revision += 1
        d = Decision(next(self._seq), True, "revoked", self.revision,
                     target_id, {"cascaded": cascaded})
        self.decisions.append(d)
        return d

    def inject(self, etype: EType, team: Optional[Team], period: int,
               turn_id: int, commit_at: float, payload: Optional[dict] = None) -> Decision:
        """测试/脚本通道：注入带历史承诺时刻的迟到事件。"""
        return self._ingest(etype, team, period, turn_id, commit_at,
                            payload or {})

    # ---------- 资格与快照 ----------
    def overtime_eligibility(self) -> dict:
        st = self.fold()
        if st.phase is not Phase.INTERMISSION:
            return {"eligible": False, "reason": "not_in_intermission"}
        if st.period < self.cfg.regulation_quarters:
            return {"eligible": False, "reason": "regulation_incomplete"}
        # 资格看累计总比分，而非单节比分
        tied = st.scores[Team.A] == st.scores[Team.B]
        if st.period == self.cfg.regulation_quarters:
            return {"eligible": tied,
                    "reason": "tied" if tied else "decided"}
        return {"eligible": tied,
                "reason": "sudden_death_tie" if tied else "decided"}

    def snapshot(self) -> dict:
        st = self.fold()
        clock = self.clock.snapshot(self._wall)
        timeout_budget = {}
        for p in range(1, max(st.period, 0) + 1):
            for team in Team:
                timeout_budget[f"p{p}_{team.value}"] = {
                    "used": st.timeout_used.get((p, team), 0),
                    "budget": _period_budget(self.cfg, p),
                }
        return {
            "revision": self.revision,
            "wall_time": round(self._wall, 4),
            "phase": st.phase.value,
            "period": st.period,
            "turn_id": st.turn,
            "possession": st.possession.value if st.possession else None,
            "score": {Team.A.value: st.scores[Team.A], Team.B.value: st.scores[Team.B]},
            "period_scores": {
                str(p): {k.value: v for k, v in ps.items()}
                for p, ps in sorted(st.period_scores.items())
            },
            "clock": clock,
            "timeout_budget": timeout_budget,
            "active_fouls": {
                fid: {"team": f["team"], "turn_id": f["turn_id"],
                      "free_throws": f.get("free_throws", [])}
                for fid, f in st.active_fouls.items()
            },
            "overtime": self.overtime_eligibility(),
            "event_count": len([e for e in self.events if e.id not in self._voided]),
            "voided_ids": sorted(self._voided),
        }

    def audit_events(self) -> list[dict]:
        out = []
        for e in self._sorted_events():
            d = e.to_dict()
            d["voided"] = e.id in self._voided
            out.append(d)
        return out

    def audit_decisions(self) -> list[dict]:
        return [d.to_dict() for d in self.decisions]

    def audit_clock(self) -> list[dict]:
        return [c.to_dict() for c in self.clock.ledger]
