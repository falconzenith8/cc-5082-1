"""完整赛事脚本：可控墙钟驱动一场 Circuit Ball，覆盖全部要求场景。

场景：末秒压哨得分、连续暂停、同分进入加时、非法重复开局、
迟到旧回合事件、犯规罚球与处罚撤销，并逐步核对球权与时钟迁移。

运行：python -m sport.demo
"""
from __future__ import annotations

from .engine import RuleEngine
from .models import EType, MatchConfig, Phase, Team


class Wall:
    """单调可控墙钟：与有效比赛时钟严格分离。"""

    def __init__(self) -> None:
        self.t = 0.0

    def advance(self, eng: RuleEngine, seconds: float, note: str = "") -> None:
        self.t += seconds
        eng.tick(self.t)
        print(f"  [墙钟 +{seconds:>4.1f}s -> {self.t:>6.1f}] {note}")


def line(title: str) -> None:
    print("\n" + "=" * 68)
    print(title)
    print("=" * 68)


def show(eng: RuleEngine) -> None:
    s = eng.snapshot()
    print(f"  rev={s['revision']:>2} | {s['phase']:<12} P{s['period'] or '-'} "
          f"T{s['turn_id']} | 比分 A {s['score']['A']}:{s['score']['B']} B "
          f"| 控球 {s['possession'] or '-'} "
          f"| 有效时钟 {s['clock']['remaining']:>5.1f}s "
          f"{'LIVE' if s['clock']['live'] else 'STOP'}")


def expect(decision, accepted: bool, label: str) -> None:
    mark = "✓" if decision.accepted == accepted else "✗"
    print(f"  {mark} {label}: {'接受' if decision.accepted else '拒绝'} "
          f"({decision.reason})")
    assert decision.accepted == accepted, f"{label} 预期不符"


def main() -> int:
    cfg = MatchConfig(
        regulation_quarters=4, quarter_seconds=30.0, ot_seconds=15.0,
        timeouts_reg=2, timeouts_ot=1,
    )
    eng = RuleEngine(cfg, wall_now=0.0)
    wall = Wall()

    line("场景 1：非法重复开局（未开赛开节 + 连续两次开局）")
    expect(eng.start_period(Team.A), False, "未开局直接开节")
    expect(eng.start_match(), True, "首次开局")
    expect(eng.start_match(), False, "重复开局")
    show(eng)

    line("场景 2：第一节 — 进球换权链 + 连续暂停 + 停表不耗回合")
    expect(eng.start_period(Team.A), True, "第一节开始，A 控球")
    wall.advance(eng, 6.0, "LIVE 6 秒")
    expect(eng.goal(Team.B), False, "无球权方 B 出手")
    expect(eng.goal(Team.A), True, "A 进球 +2，球权转 B，回合 0->1")
    show(eng)
    wall.advance(eng, 4.0, "B 控球推进")
    expect(eng.timeout(Team.B), True, "B 请求暂停（停表）")
    wall.advance(eng, 12.0, "暂停演出：墙钟走 12 秒，有效时钟冻结")
    show(eng)
    expect(eng.goal(Team.B), False, "停表期间出手被拒，不消耗回合")
    expect(eng.resume(), True, "恢复比赛")
    wall.advance(eng, 2.0, "LIVE 2 秒")
    expect(eng.timeout(Team.A), True, "A 紧接着叫暂停（连续暂停合法）")
    expect(eng.resume(), True, "再次恢复")
    wall.advance(eng, 30.0, "打到鸣笛")
    show(eng)

    line("场景 3：第二节 — 犯规罚球链与处罚撤销（只回退对应影响）")
    expect(eng.start_period(Team.B), True, "第二节开始，B 控球")
    wall.advance(eng, 5.0)
    foul = eng.foul(Team.A)                    # A 对 B 犯规
    expect(foul, True, "A 犯规，停表，B 获两次罚球")
    expect(eng.free_throw(Team.B, foul.event_id, True), True, "B 罚球 1 中 +1")
    expect(eng.free_throw(Team.B, foul.event_id, False), True, "B 罚球 2 不中")
    expect(eng.free_throw(Team.B, foul.event_id, True), False, "第三次罚球超次")
    show(eng)
    score_before = eng.snapshot()["score"].copy()
    expect(eng.revoke(foul.event_id, "录像复审：犯规不成立"), True,
           "撤销犯规，级联作废两条罚球")
    s = eng.snapshot()
    assert s["score"]["B"] == score_before["B"] - 1, "撤销只回退该犯规链的 1 分"
    print(f"  ✓ 比分仅回退罚球链：{score_before} -> {s['score']}")
    assert eng.snapshot()["phase"] == Phase.LIVE.value, "撤销犯规自动恢复 LIVE"
    print("  ✓ 撤销停表来源后时钟自动恢复 LIVE，无需额外恢复命令")
    wall.advance(eng, 30.0, "打到鸣笛")
    show(eng)

    line("场景 4：第三节 — 末秒压哨得分，承诺时刻优先于回调先后")
    expect(eng.start_period(Team.A), True, "第三节开始")
    wall.advance(eng, 28.0, "剩余 2 秒")
    # 模拟场景脚本先记录承诺、鸣笛后才送达：直接注入 commit_at=0 的迟到进球
    wall.advance(eng, 2.0, "鸣笛")
    show(eng)
    late = eng.inject(EType.GOAL, Team.A, period=3,
                      turn_id=eng.fold().turn, commit_at=0.0,
                      payload={"points": 2})
    expect(late, True, "迟到的压哨进球（commit_at=0）仍算数")
    stale = eng.inject(EType.GOAL, Team.B, period=3,
                       turn_id=eng.fold().turn, commit_at=0.5,
                       payload={"points": 2})
    expect(stale, False, "承诺晚于鸣笛的事件被拒")
    show(eng)

    line("场景 5：第四节 — 新节封印旧节，迟到旧回合事件不能改新比分，末段扳平")
    expect(eng.start_period(Team.B), True, "第四节开始（第三节封印），B 控球")
    wall.advance(eng, 6.0)
    expect(eng.goal(Team.B), True, "B 进球 +2（总比分 4:2），球权转 A")
    sealed_score = eng.snapshot()["score"].copy()
    expect(eng.inject(EType.GOAL, Team.A, period=3, turn_id=0,
                      commit_at=10.0, payload={"points": 2}),
           False, "迟到的第三节旧回合事件被拒（节已封印）")
    assert eng.snapshot()["score"] == sealed_score, "旧事件不得改动新比分"
    wall.advance(eng, 8.0)
    expect(eng.shot_miss(Team.A), True, "A 投篮不中，球权回 B")
    wall.advance(eng, 6.0)
    expect(eng.goal(Team.B), True, "B 再进一球，常规时间 4:4 平")
    wall.advance(eng, 20.0, "打完第四节鸣笛")
    show(eng)

    line("场景 6：同分进入加时")
    s = eng.snapshot()
    ot = eng.overtime_eligibility()
    print(f"  常规时间比分 {s['score']}，加时资格：{ot}")
    assert ot["eligible"], "平分后必须具备加时资格"
    print("  ✓ 平分，允许进入加时；非平分引擎会以 ot_requires_tied_regulation 拒绝")
    expect(eng.start_period(Team.A), True, "加时开始，使用加时时钟 15 秒")
    assert abs(eng.snapshot()["clock"]["remaining"] - 15.0) < 1e-6
    wall.advance(eng, 6.0)
    expect(eng.goal(Team.A), True, "加时 A 制胜球")
    wall.advance(eng, 20.0, "加时鸣笛")
    show(eng)
    assert eng.overtime_eligibility()["eligible"] is False
    print("  ✓ 加时分出胜负，不再续赛")

    line("核对：球权迁移与时钟审计")
    possession_log = [
        (e["period"], e["turn_id"], e["type"], e["team"], e["commit_at"])
        for e in eng.audit_events()
        if e["type"] in ("start_period", "goal", "shot_miss", "possession")
        and not e["voided"]
    ]
    print("  球权/回合迁移（节, 回合, 事件, 队, 承诺剩余秒）:")
    for row in possession_log:
        print("   ", row)

    clock_moves = eng.audit_clock()
    live_total = sum(
        c["game_remaining_before"] - c["game_remaining_after"]
        for c in clock_moves if c["phase"] == "LIVE"
    )
    stopped = [c for c in clock_moves
               if c["phase"] == "STOPPED"
               and c["game_remaining_before"] == c["game_remaining_after"]]
    print(f"\n  时钟迁移记录 {len(clock_moves)} 条；"
          f"LIVE 累计消耗 {live_total:.1f}s；停表冻结记录 {len(stopped)} 条")
    assert abs(eng.snapshot()["clock"]["total_live_seconds"] - live_total) < 1e-6
    print("  ✓ 墙钟停表区间未计入有效比赛时间")

    line("裁决链与得分链核对")
    accepted = [d for d in eng.audit_decisions() if d["accepted"]]
    rejected = [d for d in eng.audit_decisions() if not d["accepted"]]
    print(f"  接受 {len(accepted)} 次，拒绝 {len(rejected)} 次，最终修订号 "
          f"{eng.snapshot()['revision']}")
    scoring = [e for e in eng.audit_events()
               if e["type"] in ("goal", "free_throw") and not e["voided"]]
    calc = {Team.A.value: 0, Team.B.value: 0}
    for e in scoring:
        if e["type"] == "goal":
            calc[e["team"]] += e["payload"]["points"]
        elif e["payload"].get("made"):
            calc[e["team"]] += cfg.ft_points
    print(f"  由有效得分事件独立重算：{calc}")
    assert calc == eng.snapshot()["score"], "得分必须完全由事件链推出"
    print("  ✓ 比分与事件链折叠结果一致，无手工改分")
    print("\n赛事完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
