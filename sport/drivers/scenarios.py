"""两套驱动共用的事件场景（唯一事件源）。

统一约定（任何不一致都必须能追到具体迁移）：
- 时间单位：全部为“秒”（float）。墙钟是单调秒，赛钟 quarter_seconds/
  ot_seconds 也是秒，commit_at 是“承诺瞬间的赛钟剩余秒”。
- 得分承诺约定：命令在意图声明的墙钟点执行，commit_at 由规则内核当场从
  赛钟读取，场景只给 ref_commit_at 做精度对照，绝不反向注入承诺时刻
  （inject 通道仅在“迟到承诺”反例场景中显式使用并单独标注）。
- 排序约定：(period, 节长-commit_at, TYPE_RANK, seq)，两个驱动共用同一
  RuleEngine，因此同刻多期限的裁决顺序天然一致。

参考承诺时刻按精确时间轴预算：LIVE 每过一墙钟秒赛钟减一秒，PAUSED 不减。
"""
from __future__ import annotations

from ..models import EType, MatchConfig, Team
from .base import Intent, IntentFeed

UNIT_NOTES = {
    "time_unit": "秒（float），墙钟与有效比赛时钟同单位",
    "commitment": "commit_at = 承诺瞬间的有效赛钟剩余秒（倒计时，0.0 即鸣笛同刻）",
    "ordering": "(period, period_length-commit_at, TYPE_RANK, seq)",
    "scoring": "得分只由 GOAL/FREE_THROW 事件折叠，驱动不直接改分",
}


def _cfg() -> MatchConfig:
    # 短节长便于确定性回放；驱动实验不依赖真实墙钟速率
    return MatchConfig(
        regulation_quarters=4, quarter_seconds=20.0, ot_seconds=10.0,
        timeouts_reg=2, timeouts_ot=1, goal_points=2, ft_points=1, ft_attempts=2,
    )


def scenario_buzzer_beater() -> IntentFeed:
    """末秒得分：粗固定步把末秒出手量化到鸣笛之后，压哨球被误判。

    精确轴：A 在墙钟 19.5 出手（commit_at=0.5），20.0 鸣笛；
    step=1.0 的固定步把出手吸附到墙钟 20.0 网格，鸣笛先折叠，
    出手与迟到压哨球全部落入节间而被拒——这是固定步最关键的精度反例。
    step=0.25 与事件跳都在精确时刻处理，压哨球成立。
    """
    cfg = _cfg()
    q = cfg.quarter_seconds
    intents = [
        Intent(0.0, "start_match", lambda e: e.start_match()),
        Intent(0.0, "start_p1", lambda e: e.start_period(Team.A)),
        # 球权布置：A 先进换权给 B，B 未中把球权还给 A；此后到节末无终结
        # 动作，A 始终持球，迟到压哨 inject 才能通过球权/回合校验
        Intent(2.0, "goal_a_setup", lambda e: e.goal(Team.A),
               ref_commit_at=18.0),
        Intent(5.0, "miss_b_setup", lambda e: e.shot_miss(Team.B),
               ref_commit_at=15.0),
        # 末秒出手：精确轴 commit_at=0.5；粗步吸附到 q 网格后落入鸣笛同刻
        Intent(q - 0.5, "goal_a_last_second",
               lambda e: e.goal(Team.A), ref_commit_at=0.5),
        # 鸣笛之后才送到的压哨承诺（显式 inject，标注为迟到通道）：
        # 仅在真实末秒出手被量化吞掉的粗步上，A 仍持球，此球成立
        Intent(q + 0.8, "late_buzzer_beater",
               lambda e: e.inject(EType.GOAL, Team.A, period=1,
                                  turn_id=e.fold().turn, commit_at=0.0,
                                  payload={"points": 2}),
               ref_commit_at=0.0),
        # 承诺晚于鸣笛（commit_at>0 的迟到构造）：任何驱动都必须拒绝
        Intent(q + 0.9, "late_after_buzzer",
               lambda e: e.inject(EType.GOAL, Team.A, period=1,
                                  turn_id=e.fold().turn, commit_at=0.5,
                                  payload={"points": 2}),
               expect_accepted=False),
    ]
    return IntentFeed(
        "buzzer_beater", intents, horizon=q + 2.0,
        config_overrides={}, description="末秒出手 + 鸣笛后迟到压哨球",
    )


def scenario_long_timeout() -> IntentFeed:
    """长暂停：墙钟演出 30 秒，有效赛钟一秒不耗；空闲开销差异最明显。"""
    cfg = _cfg()
    q = cfg.quarter_seconds
    intents = [
        Intent(0.0, "start_match", lambda e: e.start_match()),
        Intent(0.0, "start_p1", lambda e: e.start_period(Team.A)),
        Intent(3.0, "goal_a", lambda e: e.goal(Team.A), ref_commit_at=17.0),
        Intent(5.0, "timeout_b", lambda e: e.timeout(Team.B),
               ref_commit_at=15.0),
        # 长暂停演出：从墙钟 5 一直停到 35，赛钟始终冻结在 15.0
        Intent(35.0, "resume", lambda e: e.resume(), ref_commit_at=15.0),
        Intent(37.0, "goal_b", lambda e: e.goal(Team.B),
               ref_commit_at=13.0),
    ]
    return IntentFeed(
        "long_timeout", intents, horizon=40.0,
        description="30 秒长暂停：停表区间的空闲醒来计数对照",
    )


def scenario_coincident_deadlines() -> IntentFeed:
    """多项期限重合：同一墙钟点犯规/罚球/多承诺重合，验证规范裁决顺序。"""
    cfg = _cfg()
    q = cfg.quarter_seconds
    intents = [
        Intent(0.0, "start_match", lambda e: e.start_match()),
        Intent(0.0, "start_p1", lambda e: e.start_period(Team.A)),
        Intent(4.0, "foul_b", lambda e: e.foul(Team.B), ref_commit_at=16.0),
        # 两次罚球与犯规全部落在墙钟 4.0 同一期限（停表，赛钟不耗）
        Intent(4.0, "ft1",
               lambda e: e.free_throw(Team.A, _foul_id(e, 0), True)),
        Intent(4.0, "ft2",
               lambda e: e.free_throw(Team.A, _foul_id(e, 0), False)),
        # 第三次罚球同刻送达，超次必须被拒（同刻多期限里的拒绝路径）
        Intent(4.0, "ft3_rejected",
               lambda e: e.free_throw(Team.A, _foul_id(e, 0), True),
               expect_accepted=False),
        Intent(5.0, "resume", lambda e: e.resume(), ref_commit_at=16.0),
        # 恢复后在 6.0 同一期限叠加进球与球权宣告，TYPE_RANK 决定折叠顺序
        Intent(6.0, "goal_a", lambda e: e.goal(Team.A), ref_commit_at=15.0),
        Intent(6.0, "possession_b", lambda e: e.possession(Team.B)),
    ]
    return IntentFeed(
        "coincident_deadlines", intents, horizon=q + 2.0,
        description="同刻多期限：犯规/罚球/超次/进球/球权重合时的 TYPE_RANK 顺序",
    )


def _foul_id(engine, index: int) -> str:
    fouls = [e for e in engine.audit_events()
             if e["type"] == EType.FOUL.value and not e["voided"]]
    return fouls[index]["id"]


def scenario_zero_duration_turn() -> IntentFeed:
    """零时长回合反例：同一墙钟点连续终结多个回合，赛钟不前进。

    事件跳与固定步在此负载下都必须依赖 seq 打破同刻平局；若内核改为
    按墙钟回调先后裁决，两个驱动都会产生不确定球权。
    """
    intents = [
        Intent(0.0, "start_match", lambda e: e.start_match()),
        Intent(0.0, "start_p1", lambda e: e.start_period(Team.A)),
        # 全部在墙钟 2.0 同刻发生：A 进 -> B 进 -> A 不中，三个零时长回合
        Intent(2.0, "goal_a_t0", lambda e: e.goal(Team.A), ref_commit_at=18.0),
        Intent(2.0, "goal_b_t1", lambda e: e.goal(Team.B), ref_commit_at=18.0),
        Intent(2.0, "miss_a_t2", lambda e: e.shot_miss(Team.A),
               ref_commit_at=18.0),
    ]
    return IntentFeed(
        "zero_duration_turn", intents, horizon=22.0,
        description="零时长回合风暴：同刻多回合，只能靠 seq 定序",
    )


def scenario_resume_instant() -> IntentFeed:
    """恢复时刻反例：暂停与恢复落在同一个固定步内。

    固定步把两个边界量化到同一个步网格点，步内墙钟增量被整格计费或漏计；
    事件跳在精确时刻各跳一次，承诺时刻无量化误差。
    """
    # step=1.0 时，pause@0.6 与 resume@0.9 都被吸附到 1.0 网格；
    # 0.6~0.9 的 0.3 秒在精确轴上属于 LIVE 消耗，因此到墙钟 5.0 时
    # 赛钟剩余 = 20 - 0.6 - (5.0-0.9) = 15.3
    intents = [
        Intent(0.0, "start_match", lambda e: e.start_match()),
        Intent(0.0, "start_p1", lambda e: e.start_period(Team.A)),
        Intent(0.6, "pause_sub_step", lambda e: e.pause("sub_step"),
               ref_commit_at=19.4),
        Intent(0.9, "resume_sub_step", lambda e: e.resume(),
               ref_commit_at=19.4),
        Intent(5.0, "goal_a", lambda e: e.goal(Team.A),
               ref_commit_at=15.3),
    ]
    return IntentFeed(
        "resume_instant", intents, horizon=22.0,
        description="亚步级暂停/恢复：量化误差可追到具体时钟迁移",
    )


def scenario_full_regulation_ot() -> IntentFeed:
    """完整常规赛 + 加时：兼容路径的端到端场景，两个驱动必须同结果。

    每节都安排节内动作，避免意图只落在节边界；第四节 2:2 平，加时 A 制胜。
    """
    cfg = _cfg()
    q, ot = cfg.quarter_seconds, cfg.ot_seconds
    intents = [
        Intent(0.0, "start_match", lambda e: e.start_match()),
        Intent(0.0, "start_p1", lambda e: e.start_period(Team.A)),
        Intent(q - 1.0, "end_p1_marker", lambda e: e.touch_noop()),
        Intent(q, "start_p2", lambda e: e.start_period(Team.B)),
        Intent(2 * q - 1.0, "end_p2_marker", lambda e: e.touch_noop()),
        Intent(2 * q, "start_p3", lambda e: e.start_period(Team.A)),
        Intent(3 * q - 1.0, "end_p3_marker", lambda e: e.touch_noop()),
        Intent(3 * q, "start_p4", lambda e: e.start_period(Team.B)),
        # 第四节 B 先进（球权在 B），A 末段扳平 2:2
        Intent(3 * q + 4.0, "goal_b_p4", lambda e: e.goal(Team.B),
               ref_commit_at=q - 4.0),
        Intent(3 * q + 14.0, "goal_a_p4", lambda e: e.goal(Team.A),
               ref_commit_at=q - 14.0),
        Intent(4 * q - 0.5, "end_p4_marker", lambda e: e.touch_noop()),
        Intent(4 * q, "start_ot", lambda e: e.start_period(Team.A)),
        Intent(4 * q + 4.0, "goal_a_ot", lambda e: e.goal(Team.A),
               ref_commit_at=ot - 4.0),
        Intent(4 * q + ot - 0.5, "ot_marker", lambda e: e.touch_noop()),
    ]
    return IntentFeed(
        "full_regulation_ot", intents, horizon=4 * q + ot + 1.0,
        description="四节平局进加时并制胜：旧接口兼容端到端核对",
    )


def scenario_dense_interrupts() -> IntentFeed:
    """事件跳不适用的负载：高频中断让期限数逼近固定步的网格密度。

    每 0.2 秒一次合法的暂停/恢复交替，期限非常密集：事件跳的“按需醒来”
    退化为比 1.0 秒粗固定步更频繁的跳跃（每次跳跃还要计算下一内部期限）。
    """
    intents = [
        Intent(0.0, "start_match", lambda e: e.start_match()),
        Intent(0.0, "start_p1", lambda e: e.start_period(Team.A)),
    ]
    t = 1.0
    for i in range(20):
        intents.append(Intent(
            t, f"pause_{i}",
            lambda e, i=i: e.pause(f"dense_pause_{i}")))
        t += 0.2
        intents.append(Intent(
            t, f"resume_{i}",
            lambda e, i=i: e.resume()))
        t += 0.2
    return IntentFeed(
        "dense_interrupts", intents, horizon=22.0,
        description="高频中断风暴：事件跳优势消失的反例负载",
    )


def all_scenarios() -> list[IntentFeed]:
    return [
        scenario_buzzer_beater(),
        scenario_long_timeout(),
        scenario_coincident_deadlines(),
        scenario_zero_duration_turn(),
        scenario_resume_instant(),
        scenario_full_regulation_ot(),
        scenario_dense_interrupts(),
    ]
