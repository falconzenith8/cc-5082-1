"""时钟驱动对照自测：固定逻辑步 vs 事件跳到下一期限。

运行：python -m sport.drivers.tests
覆盖：末秒压哨、长暂停空闲开销、同刻多期限裁决顺序、零时长回合反例、
亚步恢复反例、高频中断反例，以及两驱动在正常负载下的最终状态等价性。
"""
from __future__ import annotations

from ..engine import RuleEngine
from ..models import MatchConfig
from .event_jump import EventJumpDriver
from .fixed_step import FixedStepDriver
from . import scenarios
from .base import IntentFeed


def _cfg() -> MatchConfig:
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


def _run(driver_cls, feed: IntentFeed, **kw):
    eng = RuleEngine(_cfg(), wall_now=0.0)
    drv = driver_cls(eng, **kw) if kw else driver_cls(eng)
    return drv, drv.run_feed(feed.copy())


def test_long_timeout_idle_overhead(ch: Check) -> None:
    feed = scenarios.scenario_long_timeout()
    _, m_fixed = _run(FixedStepDriver, feed, step=1.0)
    _, m_jump = _run(EventJumpDriver, feed)
    # 30 秒停表演出：固定步在演出期间逐格空转，事件跳零次醒来
    ch.ok(m_fixed.wakeups == 40, "固定步 40 次醒来（含长暂停空转）")
    ch.ok(m_jump.wakeups == 5, "事件跳仅在 5 个真实期限醒来")
    ch.ok(m_jump.wakeups < m_fixed.wakeups, "长暂停下事件跳空闲开销显著更低")
    # 两驱动赛钟 LIVE 累计消耗一致：停表区间都不计费
    ch.ok(abs(m_fixed.final_snapshot["clock"]["total_live_seconds"]
              - m_jump.final_snapshot["clock"]["total_live_seconds"]) < 1e-9,
          "停表不耗有效时间，两驱动 LIVE 累计一致")
    ch.ok(m_fixed.final_snapshot["score"] == m_jump.final_snapshot["score"]
          == {"A": 2, "B": 2}, "长暂停场景比分一致")
    print("✓ 长暂停：固定步空转 40 次 vs 事件跳 5 次，赛钟冻结且结果一致")


def test_buzzer_beater_quantization(ch: Check) -> None:
    feed = scenarios.scenario_buzzer_beater()
    _, m_coarse = _run(FixedStepDriver, feed, step=1.0)
    _, m_fine = _run(FixedStepDriver, feed, step=0.25)
    _, m_jump = _run(EventJumpDriver, feed)
    # 粗固定步：末秒真实出手被量化到鸣笛网格后拒掉，只能靠迟到 inject
    # 通道救回分数；细步/事件跳在 LIVE 中直接接受真实出手
    coarse_shot = [v for v in m_coarse.verdicts
                   if v["label"] == "goal_a_last_second"][0]
    ch.ok(not coarse_shot["accepted"]
          and coarse_shot["reason"] == "shot_requires_live",
          "粗固定步误判：末秒出手在量化后的鸣笛点被拒")
    coarse_err = max(e["abs_error"] for e in m_coarse.commit_errors
                     if e["label"] == "goal_a_last_second")
    ch.ok(abs(coarse_err - 0.5) < 1e-9, "粗步量化误差 0.5 秒可追到承诺记录")
    coarse_late = [v for v in m_coarse.verdicts
                   if v["label"] == "late_buzzer_beater"][0]
    ch.ok(coarse_late["accepted"], "粗步上压哨迟到球经 inject 通道救回")
    fine_shot = [v for v in m_fine.verdicts
                 if v["label"] == "goal_a_last_second"][0]
    jump_shot = [v for v in m_jump.verdicts
                 if v["label"] == "goal_a_last_second"][0]
    ch.ok(fine_shot["accepted"] and jump_shot["accepted"],
          "细步/事件跳的末秒出手在 LIVE 中被接受")
    # 三驱动最终比分相同（粗步靠救回、细步/事件跳靠真实出手），但裁决路径不同
    ch.ok(m_coarse.final_snapshot["score"]["A"]
          == m_fine.final_snapshot["score"]["A"]
          == m_jump.final_snapshot["score"]["A"] == 4,
          "比分相同但粗步的得分来源是迟到救回而非真实出手")
    # 承诺晚于鸣笛的迟到事件在所有驱动上都被拒
    for m, name in ((m_coarse, "coarse"), (m_fine, "fine"), (m_jump, "jump")):
        late = [v for v in m.verdicts if v["label"] == "late_after_buzzer"][0]
        ch.ok(not late["accepted"], f"{name} 拒绝鸣笛后承诺事件")
    print("✓ 末秒压哨：粗步量化误判（误差 0.5s），细步/事件跳精确裁决")


def test_coincident_deadline_order(ch: Check) -> None:
    feed = scenarios.scenario_coincident_deadlines()
    _, m_fixed = _run(FixedStepDriver, feed, step=1.0)
    _, m_jump = _run(EventJumpDriver, feed)
    # 同刻多期限的规范折叠顺序两驱动必须完全相同
    ch.ok(m_fixed.deadline_order == m_jump.deadline_order,
          "同刻期限裁决顺序两驱动一致")
    group = m_jump.deadline_order[0]
    ch.ok(group["order"][0] == "foul", "TYPE_RANK 保证犯规先于罚球折叠")
    ch.ok(group["order"][-1] == "free_throw", "罚球排在期限末端")
    # 第三次罚球超次被拒，两个驱动都拒绝
    for m in (m_fixed, m_jump):
        ft3 = [v for v in m.verdicts if v["label"] == "ft3_rejected"][0]
        ch.ok(not ft3["accepted"] and ft3["reason"] == "free_throw_attempts_exceeded",
              "同刻超次罚球被拒")
    ch.ok(m_fixed.final_snapshot["score"] == m_jump.final_snapshot["score"],
          "同刻多期限场景比分一致")
    print("✓ 多期限重合：TYPE_RANK 规范顺序在两驱动上完全一致")


def test_zero_duration_turn_counterexample(ch: Check) -> None:
    feed = scenarios.scenario_zero_duration_turn()
    _, m_fixed = _run(FixedStepDriver, feed, step=1.0)
    _, m_jump = _run(EventJumpDriver, feed)
    # 同刻三个零时长回合：seq 定序，球权链确定
    ch.ok(m_fixed.final_snapshot == m_jump.final_snapshot or
          m_fixed.final_snapshot["score"] == m_jump.final_snapshot["score"],
          "零时长回合两驱动比分一致")
    s = m_jump.final_snapshot
    ch.ok(s["score"] == {"A": 2, "B": 2}, "零时长回合比分 2:2")
    ch.ok(s["turn_id"] == 3, "三个同刻回合把 turn 推进到 3")
    ch.ok(s["possession"] == "B", "最后 A 不中后球权确定归 B")
    # 同刻三回合发生在墙钟 2.0，当时赛钟剩余恰为 18（同刻不额外耗时）；
    # 场景跑到 horizon=22 后鸣笛归零，LIVE 累计必须恰好等于节长 20
    at_two = [e for e in m_jump.commit_errors
              if e["label"] == "miss_a_t2"]
    ch.ok(bool(at_two) and abs(at_two[0]["actual_commit_at"] - 18.0) < 1e-9,
          "零时长回合承诺时刻同为 18 秒，同刻不额外消耗赛钟")
    ch.ok(all(abs(e["actual_commit_at"] - 18.0) < 1e-9
              for e in m_jump.commit_errors),
          "三个同刻回合的承诺时刻完全相同（18 秒）")
    ch.ok(abs(s["clock"]["total_live_seconds"] - 20.0) < 1e-9,
          "LIVE 累计恰为节长，零时长回合不产生额外计费")
    ch.ok(s["clock"]["remaining"] == 0.0 and s["phase"] == "INTERMISSION",
          "跑完 horizon 后正常鸣笛进入节间")
    print("✓ 零时长回合反例：同刻多回合靠 seq 确定球权，赛钟不前进")


def test_resume_instant_counterexample(ch: Check) -> None:
    feed = scenarios.scenario_resume_instant()
    _, m_coarse = _run(FixedStepDriver, feed, step=1.0)
    _, m_fine = _run(FixedStepDriver, feed, step=0.25)
    _, m_jump = _run(EventJumpDriver, feed)
    # 亚步暂停/恢复：固定步承诺误差随步长缩小，事件跳误差为 0
    ch.ok(m_coarse.max_commit_error >= 0.4 - 1e-9,
          "粗步亚步恢复误差约 0.4 秒")
    ch.ok(m_fine.max_commit_error < m_coarse.max_commit_error,
          "细步误差小于粗步")
    ch.ok(m_jump.max_commit_error < 1e-9, "事件跳亚步恢复零量化误差")
    # 误差可追到具体迁移：粗步把 0.6/0.9 都吸附到墙钟 1.0 网格
    coarse_pause = [c for c in m_coarse.clock_ledger
                    if c["note"] == "sub_step"][0]
    ch.ok(abs(coarse_pause["wall_at"] - 1.0) < 1e-9,
          "粗步暂停迁移被量化到墙钟 1.0（迁移可追踪）")
    jump_pause = [c for c in m_jump.clock_ledger
                  if c["note"] == "sub_step"][0]
    ch.ok(abs(jump_pause["wall_at"] - 0.6) < 1e-9,
          "事件跳暂停迁移保留精确墙钟 0.6")
    print("✓ 恢复时刻反例：量化误差随步长变化，且可追到具体时钟迁移")


def test_dense_interrupts_event_jump_loses(ch: Check) -> None:
    feed = scenarios.scenario_dense_interrupts()
    _, m_coarse = _run(FixedStepDriver, feed, step=1.0)
    _, m_jump = _run(EventJumpDriver, feed)
    # 高频中断：事件跳醒来次数反超粗固定步——按需跳跃优势消失的负载
    ch.ok(m_jump.wakeups > m_coarse.wakeups,
          "高频中断下事件跳醒来数反超粗固定步")
    ch.ok(m_jump.wakeups == 41 and m_coarse.wakeups == 22,
          "事件跳 41 次 vs 粗步 22 次（事件跳不适用负载）")
    print("✓ 高频中断反例：事件跳 41 次醒来 > 粗固定步 22 次，优势反转")


def test_full_regulation_ot_equivalence(ch: Check) -> None:
    feed = scenarios.scenario_full_regulation_ot()
    drivers = [
        ("fixed1", FixedStepDriver(RuleEngine(_cfg(), 0.0), step=1.0)),
        ("fixed025", FixedStepDriver(RuleEngine(_cfg(), 0.0), step=0.25)),
        ("jump", EventJumpDriver(RuleEngine(_cfg(), 0.0))),
    ]
    snaps = {}
    for name, drv in drivers:
        m = drv.run_feed(feed.copy())
        snaps[name] = m.final_snapshot
    core_keys = ("phase", "period", "turn_id", "possession", "score",
                 "event_count")
    for k in core_keys:
        vals = {name: s[k] for name, s in snaps.items()}
        ch.ok(len({str(v) for v in vals.values()}) == 1,
              f"完整常规赛+加时字段 {k} 三驱动一致")
    ch.ok(snaps["jump"]["period"] == 5, "进入加时（第 5 节）")
    ch.ok(snaps["jump"]["score"] == {"A": 4, "B": 2}, "加时 A 制胜 4:2")
    print("✓ 完整常规赛+加时：三驱动裁决完全一致，旧接口链路兼容")


def test_monotonic_wall_required(ch: Check) -> None:
    eng = RuleEngine(_cfg(), 0.0)
    drv = EventJumpDriver(eng)
    drv.advance_to(5.0)
    raised = False
    try:
        drv.advance_to(4.0)
    except ValueError:
        raised = True
    ch.ok(raised, "事件跳拒绝倒退墙钟")
    print("✓ 墙钟单调性保护")


def main() -> int:
    ch = Check()
    tests = [
        test_long_timeout_idle_overhead,
        test_buzzer_beater_quantization,
        test_coincident_deadline_order,
        test_zero_duration_turn_counterexample,
        test_resume_instant_counterexample,
        test_dense_interrupts_event_jump_loses,
        test_full_regulation_ot_equivalence,
        test_monotonic_wall_required,
    ]
    for t in tests:
        t(ch)
    print(f"\n{ch.passed} 项断言通过，{len(ch.failed)} 项失败")
    return 0 if not ch.failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
