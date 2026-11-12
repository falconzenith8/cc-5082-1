"""规则内核自测：以可控墙钟驱动，核对球权、时钟迁移与得分链。

运行：python -m sport.tests
"""
from __future__ import annotations

from .engine import RuleEngine
from .models import EType, MatchConfig, Phase, Team


def cfg() -> MatchConfig:
    return MatchConfig(
        regulation_quarters=4, quarter_seconds=20.0, ot_seconds=10.0,
        timeouts_reg=2, timeouts_ot=1,
    )


class Check:
    def __init__(self) -> None:
        self.passed = 0
        self.failed: list[str] = []

    def ok(self, cond: bool, label: str) -> None:
        if cond:
            self.passed += 1
        else:
            self.failed.append(label)
            raise AssertionError(label)

    def acc(self, d) -> None:
        self.ok(d.accepted, f"expected accepted: {d.reason}")

    def rej(self, d, fragment: str) -> None:
        self.ok((not d.accepted) and fragment in d.reason,
                f"expected reject {fragment}, got {d.reason}")


def test_illegal_double_start(ch: Check) -> None:
    eng = RuleEngine(cfg(), wall_now=100.0)
    ch.acc(eng.start_match())
    ch.rej(eng.start_match(), "illegal_restart")
    # 未开局不能开节
    eng2 = RuleEngine(cfg(), wall_now=0.0)
    ch.rej(eng2.start_period(Team.A), "match_not_started")
    print("✓ 非法重复开局 / 未开局开节被拒绝")


def test_clock_stop_and_resume(ch: Check) -> None:
    eng = RuleEngine(cfg(), wall_now=0.0)
    wall = [0.0]

    def advance(seconds: float) -> None:
        wall[0] += seconds
        eng.tick(wall[0])

    eng.start_match()
    eng.start_period(Team.A)
    # LIVE：墙钟推进 5 秒，有效时钟同步消耗 5 秒
    advance(5.0)
    s = eng.snapshot()
    ch.ok(abs(s["clock"]["remaining"] - 15.0) < 1e-6, "live drains game clock")
    ch.ok(s["clock"]["live"] is True, "clock live")
    # 暂停后墙钟再走 8 秒，有效时钟冻结
    eng.pause()
    advance(8.0)
    s = eng.snapshot()
    ch.ok(abs(s["clock"]["remaining"] - 15.0) < 1e-6, "paused freezes game clock")
    ch.ok(s["phase"] == Phase.PAUSED.value, "phase paused")
    # 恢复后从 15 秒继续扣，墙钟再走 5 秒 -> 剩 10 秒
    eng.resume()
    advance(5.0)
    s = eng.snapshot()
    ch.ok(abs(s["clock"]["remaining"] - 10.0) < 1e-6, "resume continues correctly")
    ch.ok(abs(s["clock"]["total_live_seconds"] - 10.0) < 1e-6,
          "live time excludes stopped interval")
    # 审计：存在 STOPPED 且剩余不变的迁移
    stops = [c for c in eng.audit_clock() if c["phase"] == "STOPPED"]
    ch.ok(any(c["game_remaining_before"] == c["game_remaining_after"] for c in stops),
          "stopped ledger entry freezes clock")
    print("✓ 墙钟与有效时钟分离，停表冻结、恢复续走，审计迁移存在")


def test_possession_and_score_chain(ch: Check) -> None:
    eng = RuleEngine(cfg(), wall_now=0.0)
    eng.start_match()
    eng.start_period(Team.A)
    eng.tick(2.0)
    ch.rej(eng.goal(Team.B), "team_without_possession")
    ch.acc(eng.goal(Team.A))
    s = eng.snapshot()
    ch.ok(s["score"]["A"] == 2 and s["possession"] == "B" and s["turn_id"] == 1,
          "goal scores and flips possession")
    # 同一回合重复进球不可能：turn 已推进；A 在 B 的回合出手被拒
    ch.rej(eng.goal(Team.A), "team_without_possession")
    # B 未中，球权回 A，无得分
    ch.acc(eng.shot_miss(Team.B))
    s = eng.snapshot()
    ch.ok(s["score"]["B"] == 0 and s["possession"] == "A" and s["turn_id"] == 2,
          "miss flips without score")
    # 得分链全部由事件折叠，无手工改分入口
    goals = [e for e in eng.audit_events() if e["type"] == "goal" and not e["voided"]]
    ch.ok(len(goals) == 1 and goals[0]["payload"]["points"] == 2,
          "score derives solely from event chain")
    print("✓ 球权校验、进球换权、未中换权、回合推进与得分链")


def test_consecutive_timeouts(ch: Check) -> None:
    eng = RuleEngine(cfg(), wall_now=0.0)
    wall = [0.0]

    def advance(seconds: float) -> None:
        wall[0] += seconds
        eng.tick(wall[0])

    eng.start_match()
    eng.start_period(Team.A)
    advance(3.0)
    ch.acc(eng.timeout(Team.A))   # A 暂停，停表
    advance(10.0)                # 演出时间
    s = eng.snapshot()
    ch.ok(abs(s["clock"]["remaining"] - 17.0) < 1e-6, "timeout performance consumes no game time")
    ch.rej(eng.goal(Team.A), "shot_requires_live")  # 停表演出不消耗回合
    ch.acc(eng.resume())
    advance(2.0)
    ch.acc(eng.timeout(Team.B))   # 另一队紧接着可再叫暂停
    s = eng.snapshot()
    ch.ok(s["timeout_budget"]["p1_A"]["used"] == 1
          and s["timeout_budget"]["p1_B"]["used"] == 1, "consecutive timeouts both allowed")
    # A 用掉第二节内暂停
    eng.resume()
    advance(1.0)
    ch.acc(eng.timeout(Team.A))
    eng.resume()
    advance(1.0)
    ch.rej(eng.timeout(Team.A), "timeout_budget_exhausted")  # 预算耗尽
    print("✓ 连续暂停、停表不耗回合、暂停预算耗尽拒绝")


def test_buzzer_beater_commitment_ordering(ch: Check) -> None:
    eng = RuleEngine(cfg(), wall_now=0.0)
    eng.start_match()
    eng.start_period(Team.A)
    # 推进到自然鸣笛（单调墙钟）
    eng.tick(20.0)
    s = eng.snapshot()
    ch.ok(s["phase"] == Phase.INTERMISSION.value and s["clock"]["remaining"] == 0.0,
          "auto buzzer enters intermission")
    # 网络迟到：进球承诺时刻为 0.0（鸣笛瞬间），到达在鸣笛回调之后
    d = eng.inject(EType.GOAL, Team.A, period=1, turn_id=s["turn_id"],
                   commit_at=0.0, payload={"points": 2})
    ch.acc(d)
    s = eng.snapshot()
    ch.ok(s["score"]["A"] == 2, "buzzer beater counts despite late arrival")
    # 承诺在鸣笛之后（commit_at>0 的迟到构造）必须被拒
    d = eng.inject(EType.GOAL, Team.B, period=1, turn_id=s["turn_id"],
                   commit_at=0.5, payload={"points": 2})
    ch.ok(not d.accepted and d.reason in
          ("committed_after_buzzer", "stale_turn_id"),
          f"post-buzzer late event rejected, got {d.reason}")
    # 节间不能改球权/暂停
    ch.rej(eng.possession(Team.B), "possession_requires_live")
    ch.rej(eng.timeout(Team.A), "timeout_in_intermission")
    print("✓ 末秒压哨球按承诺时刻裁决，迟到回调不影响；鸣笛后事件被拒")


def test_period_sealing_stale_turn(ch: Check) -> None:
    eng = RuleEngine(cfg(), wall_now=0.0)
    wall = [0.0]

    def advance(seconds: float) -> None:
        wall[0] += seconds
        eng.tick(wall[0])

    eng.start_match()
    eng.start_period(Team.A)
    advance(20.0)
    # 进入第二节，第一节被封印
    eng.start_period(Team.B)
    ch.acc(eng.goal(Team.B))
    s2 = eng.snapshot()
    # 迟到的第一节旧回合事件
    ch.rej(eng.inject(EType.GOAL, Team.A, period=1, turn_id=0,
                      commit_at=5.0, payload={"points": 2}),
           "period_sealed_late_event")
    s = eng.snapshot()
    ch.ok(s["score"] == s2["score"], "stale old-period event cannot change new score")
    ch.ok(s["period"] == 2 and s["turn_id"] == 1, "new period untouched")
    print("✓ 新节封印旧节，迟到旧回合事件不能改动新比分")


def test_foul_revocation_cascade(ch: Check) -> None:
    eng = RuleEngine(cfg(), wall_now=0.0)
    eng.start_match()
    eng.start_period(Team.A)
    eng.tick(2.0)
    foul = eng.foul(Team.B)          # B 对 A 犯规，停表
    ch.acc(foul)
    foul_id = foul.event_id
    ch.acc(eng.free_throw(Team.A, foul_id, made=True))   # +1
    ch.acc(eng.free_throw(Team.A, foul_id, made=False))
    s = eng.snapshot()
    ch.ok(s["score"]["A"] == 1, "free throw made scores one")
    # 第三次罚球超次数
    ch.rej(eng.free_throw(Team.A, foul_id, True), "free_throw_attempts_exceeded")
    # 撤销犯规：级联作废两条罚球，只回退该事件链
    d = eng.revoke(foul_id, "review: no foul")
    ch.acc(d)
    ch.ok(set(d.detail["cascaded"]) and all(
        x in eng.snapshot()["voided_ids"] for x in d.detail["cascaded"]),
          "free throws cascaded void")
    s = eng.snapshot()
    ch.ok(s["score"]["A"] == 0, "revocation rolls back only the foul chain")
    # 撤销不存在 / 重复撤销
    ch.rej(eng.revoke("nope"), "event_not_found")
    ch.rej(eng.revoke(foul_id), "already_voided")
    print("✓ 犯规停表、罚球链、超次拒绝、撤销级联与仅回退对应影响")


def test_goal_revocation_restores_chain(ch: Check) -> None:
    eng = RuleEngine(cfg(), wall_now=0.0)
    eng.start_match()
    eng.start_period(Team.A)
    g = eng.goal(Team.A)
    ch.ok(eng.snapshot()["score"]["A"] == 2, "goal before revoke")
    # 下一回合已经出现终结动作 -> 撤销被依赖检查拒绝
    eng.shot_miss(Team.B)
    ch.rej(eng.revoke(g.event_id), "dependent_events_exist")
    print("✓ 后续回合已推进时撤销被拒绝，保护回合链")


def test_overtime_eligibility(ch: Check) -> None:
    eng = RuleEngine(cfg(), wall_now=0.0)
    wall = [0.0]

    def advance(seconds: float) -> None:
        wall[0] += seconds
        eng.tick(wall[0])

    eng.start_match()
    # 前三节无得分
    for p in range(1, 4):
        eng.start_period(Team.A)
        advance(20.0)
    # 第四节：A 先进，B 末秒扳平
    eng.start_period(Team.A)
    advance(4.0)
    eng.goal(Team.A)                       # A 2，球权转 B（剩 16 秒）
    advance(10.0)
    eng.goal(Team.B)                       # B 2（剩 6 秒，球权转 A）
    advance(6.0)                          # 鸣笛，2:2
    s = eng.snapshot()
    ch.ok(s["phase"] == Phase.INTERMISSION.value and s["score"] == {"A": 2, "B": 2},
          "regulation ends tied")
    ot = eng.overtime_eligibility()
    ch.ok(ot["eligible"] is True, "tie grants overtime eligibility")
    ch.acc(eng.start_period(Team.A))
    s = eng.snapshot()
    ch.ok(s["period"] == 5 and abs(s["clock"]["remaining"] - 10.0) < 1e-6,
          "overtime uses OT clock length")
    # 非平分不能进加时（独立引擎验证资格门）
    eng2 = RuleEngine(cfg(), wall_now=0.0)
    w2 = [0.0]
    eng2.start_match()
    for p in range(1, 5):
        eng2.start_period(Team.A)
        if p == 4:
            eng2.goal(Team.A)
        w2[0] += 20.0
        eng2.tick(w2[0])
    ch.ok(eng2.overtime_eligibility()["eligible"] is False, "no OT when decided")
    ch.rej(eng2.start_period(Team.A), "ot_requires_tied_regulation")
    # 加时 A 制胜
    advance(4.0)
    eng.goal(Team.A)
    advance(10.0)
    ch.ok(eng.snapshot()["score"] == {"A": 4, "B": 2}, "OT winner score")
    ch.ok(eng.overtime_eligibility()["eligible"] is False, "decided OT no further period")
    print("✓ 平分进入加时、加时时钟、非平分禁入加时、加时制胜")


def test_deterministic_out_of_order_delivery(ch: Check) -> None:
    """两台引擎接收相同事件，但网络回调顺序相反，最终状态必须一致。"""
    def build(order_swap: bool) -> dict:
        eng = RuleEngine(cfg(), wall_now=0.0)
        eng.start_match()
        eng.start_period(Team.A)
        events = [
            (EType.GOAL, Team.A, 1, 0, 18.0, {"points": 2}),
            (EType.GOAL, Team.B, 1, 1, 15.0, {"points": 2}),
            (EType.SHOT_MISS, Team.A, 1, 2, 9.0, {}),
            # 压哨球与鸣笛同刻
            (EType.GOAL, Team.B, 1, 3, 0.0, {"points": 2}),
        ]
        buzzer = (EType.BUZZER, None, 1, 3, 0.0, {"auto": True})
        beater = events[-1]
        if order_swap:
            # 回调乱序：鸣笛先到，压哨球迟到（其余事件顺序不变）
            seq = events[:-1] + [buzzer, beater]
        else:
            seq = events + [buzzer]
        for etype, team, period, turn, commit_at, payload in seq:
            d = eng.inject(etype, team, period, turn, commit_at, payload)
            assert d.accepted, f"{etype} @{commit_at}: {d.reason}"
        return eng.snapshot()
    s1 = build(False)
    s2 = build(True)
    keys = ["score", "period", "turn_id", "possession", "phase", "event_count"]
    for k in keys:
        ch.ok(s1[k] == s2[k], f"order-independent state field {k}")
    ch.ok(s1["score"] == {"A": 2, "B": 4}, "buzzer beater included either order")
    print("✓ 承诺时刻裁决：乱序回调产出相同比分与球权")


def test_revision_monotonic(ch: Check) -> None:
    eng = RuleEngine(cfg(), wall_now=0.0)
    eng.start_match()
    eng.start_period(Team.A)
    r0 = eng.snapshot()["revision"]
    eng.goal(Team.A)
    r1 = eng.snapshot()["revision"]
    ch.ok(r1 == r0 + 1, "accepted event bumps revision")
    before = eng.snapshot()["revision"]
    # 球权在 B，A 再出手属于无球权非法事件，必须被拒且不动修订号
    eng.goal(Team.A)
    ch.ok(eng.snapshot()["revision"] == before, "rejected event keeps revision")
    print("✓ 修订号只在接受变更时递增")


def main() -> int:
    ch = Check()
    tests = [
        test_illegal_double_start,
        test_clock_stop_and_resume,
        test_possession_and_score_chain,
        test_consecutive_timeouts,
        test_buzzer_beater_commitment_ordering,
        test_period_sealing_stale_turn,
        test_foul_revocation_cascade,
        test_goal_revocation_restores_chain,
        test_overtime_eligibility,
        test_deterministic_out_of_order_delivery,
        test_revision_monotonic,
    ]
    for t in tests:
        t(ch)
    print(f"\n{ch.passed} 项断言通过，{len(ch.failed)} 项失败")
    return 0 if not ch.failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
