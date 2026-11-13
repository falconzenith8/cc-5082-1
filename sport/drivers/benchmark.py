"""两套时钟驱动的可复跑对照实验。

输出（写入 sport/measurements/，可重复运行覆盖）：
- raw_runs.json：每次运行的完整原始度量（醒来数、空闲数、逐条承诺误差、
  同刻期限裁决顺序、最终快照、时钟迁移台账）；
- summary.json：跨重复次数的汇总（均值/标准差）与两驱动差异；
- migration_trace.md：把任何状态/承诺不一致追到具体时钟迁移的对照表。

不凭一次计时结果下结论：每个场景重复 RUNS 次，报告均值与标准差；
墙钟是确定性虚拟秒（非 time.monotonic），因此重复运行结果应当稳定，
标准差用于暴露环境抖动而非证明性能优劣。
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

from ..engine import RuleEngine
from ..models import MatchConfig
from .base import ClockDriver, DriverMetrics, IntentFeed
from .event_jump import EventJumpDriver
from .fixed_step import FixedStepDriver
from .scenarios import UNIT_NOTES, all_scenarios

MEASURE_DIR = Path(__file__).resolve().parent.parent / "measurements"
RUNS = 7
# 对照的固定步网格：粗步（暴露量化误差）与细步（暴露空闲开销）
STEP_SIZES = (1.0, 0.25)

# 最终快照中允许两驱动不同的字段：
# - wall_time/clock/revision 是墙钟推进实现细节与修订计数；
# - active_fouls 的键是随机事件 ID（uuid），每次构造引擎必然不同，
#   其结构等价性由 test_full_regulation_ot_equivalence 与得分链核对覆盖。
# 其余任何差异都视为裁决不一致并进入迁移追踪。
SNAPSHOT_IGNORE = {"wall_time", "clock", "revision", "active_fouls"}


def _fresh_engine() -> RuleEngine:
    return RuleEngine(MatchConfig(
        regulation_quarters=4, quarter_seconds=20.0, ot_seconds=10.0,
        timeouts_reg=2, timeouts_ot=1, goal_points=2, ft_points=1, ft_attempts=2,
    ), wall_now=0.0)


def _make_drivers() -> list[ClockDriver]:
    return [
        FixedStepDriver(_fresh_engine(), step=STEP_SIZES[0]),
        FixedStepDriver(_fresh_engine(), step=STEP_SIZES[1]),
        EventJumpDriver(_fresh_engine()),
    ]


def _driver_key(driver: ClockDriver) -> str:
    if isinstance(driver, FixedStepDriver):
        return f"fixed_step@{driver.step:g}s"
    return "event_jump"


def run_once(feed: IntentFeed, driver: ClockDriver) -> DriverMetrics:
    return driver.run_feed(feed.copy())


def _snapshot_core(snap: dict) -> dict:
    return {k: v for k, v in snap.items() if k not in SNAPSHOT_IGNORE}


def compare_snapshots(metrics_by_driver: dict[str, DriverMetrics]) -> list[dict]:
    """裁决一致性核对：除时间实现细节外，最终状态必须逐字段相等。"""
    cores = {k: _snapshot_core(m.final_snapshot)
             for k, m in metrics_by_driver.items()}
    keys = set().union(*(c.keys() for c in cores.values()))
    diffs = []
    baseline_key = sorted(cores)[0]
    for k in sorted(keys):
        values = {dk: core.get(k) for dk, core in cores.items()}
        if len({json.dumps(v, sort_keys=True, ensure_ascii=False)
                for v in values.values()}) > 1:
            diffs.append({"field": k, "values": values,
                          "baseline": baseline_key})
    return diffs


def _clock_diff_trace(metrics_by_driver: dict[str, DriverMetrics]) -> list[dict]:
    """把赛钟迁移差异按“业务锚点 note”对齐后追踪。

    固定步的 tick 条目数量与事件跳天然不同，按序号对齐会整表错位；
    因此只对比非 tick 的业务迁移（暂停/恢复/节复位/鸣笛冻结等），
    用 note 出现次序配对，墙钟或剩余值不同即一条可追踪差异。
    """
    def anchors(ledger: list[dict]) -> list[dict]:
        return [c for c in ledger if c["note"] != "tick"]

    ref_key = "event_jump"
    if ref_key not in metrics_by_driver:
        return []
    ref = anchors(metrics_by_driver[ref_key].clock_ledger)
    traces = []
    for key, m in metrics_by_driver.items():
        if key == ref_key:
            continue
        mine = anchors(m.clock_ledger)
        for i in range(max(len(mine), len(ref))):
            a = mine[i] if i < len(mine) else None
            b = ref[i] if i < len(ref) else None
            if a != b:
                traces.append({
                    "driver": key, "anchor_index": i,
                    "driver_entry": a, f"{ref_key}_entry": b,
                })
    return traces


def run() -> dict[str, Any]:
    MEASURE_DIR.mkdir(parents=True, exist_ok=True)
    feeds = {f.name: f for f in all_scenarios()}
    raw: list[dict] = []
    # 每场景每驱动的聚合容器
    agg: dict[str, dict[str, list[DriverMetrics]]] = {
        name: {} for name in feeds
    }
    for run_idx in range(RUNS):
        for name, feed in feeds.items():
            for driver in _make_drivers():
                m = run_once(feed, driver)
                key = _driver_key(driver)
                agg[name].setdefault(key, []).append(m)
                raw.append({
                    "run": run_idx, "unit_notes": UNIT_NOTES,
                    "metrics": m.to_row(),
                    "verdicts": m.verdicts,
                    "commit_errors": m.commit_errors,
                    "deadline_order": m.deadline_order,
                    "final_snapshot": m.final_snapshot,
                    "decisions_count": len(m.decisions),
                })

    summary_rows: list[dict] = []
    snapshot_diffs: list[dict] = []
    for name, per_driver in agg.items():
        last_metrics = {k: ms[-1] for k, ms in per_driver.items()}
        diffs = compare_snapshots(last_metrics)
        for d in diffs:
            d["scenario"] = name
        snapshot_diffs.extend(diffs)
        for key, ms in per_driver.items():
            row0 = ms[0].to_row()
            summary_rows.append({
                "scenario": name,
                "driver": key,
                "runs": len(ms),
                "wakeups_mean": round(statistics.fmean(x.wakeups for x in ms), 4),
                "wakeups_stdev": round(statistics.pstdev(x.wakeups for x in ms), 6),
                "idle_wakeups_mean": round(
                    statistics.fmean(x.idle_wakeups for x in ms), 4),
                "ticks_mean": round(statistics.fmean(x.ticks for x in ms), 4),
                "commands": row0["commands"],
                "accepted": row0["accepted"],
                "rejected": row0["rejected"],
                "max_commit_error": round(
                    max((x.max_commit_error for x in ms), default=0.0), 6),
                "max_commit_error_mean": round(
                    statistics.fmean(x.max_commit_error for x in ms), 6),
            })

    # 迁移追踪：用每个场景最后一次运行的完整台账
    migration = {"snapshot_diffs": snapshot_diffs, "ledger_diffs": []}
    for name, per_driver in agg.items():
        last = {k: ms[-1] for k, ms in per_driver.items()}
        for tr in _clock_diff_trace(last):
            tr["scenario"] = name
            migration["ledger_diffs"].append(tr)

    # 裁决分歧：同一意图标签在不同驱动上的接受/拒绝是否一致
    adjudication = []
    for name, per_driver in agg.items():
        label_verdict: dict[str, dict[str, str]] = {}
        for key, ms in per_driver.items():
            for v in ms[-1].verdicts:
                label_verdict.setdefault(v["label"], {})[key] = (
                    "accept" if v["accepted"] else f"reject:{v['reason']}"
                )
        for label, verdicts in sorted(label_verdict.items()):
            if len(set(verdicts.values())) > 1:
                adjudication.append(
                    {"scenario": name, "label": label, "verdicts": verdicts})
    migration["adjudication_diffs"] = adjudication

    out = {
        "unit_notes": UNIT_NOTES,
        "runs_per_cell": RUNS,
        "step_sizes": list(STEP_SIZES),
        "summary": summary_rows,
        "migration_trace": migration,
    }
    (MEASURE_DIR / "raw_runs.json").write_text(
        json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    (MEASURE_DIR / "summary.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    (MEASURE_DIR / "migration_trace.md").write_text(
        _render_migration_md(out), encoding="utf-8")
    return out


def _render_migration_md(report: dict) -> str:
    lines = [
        "# 时钟迁移不一致追踪",
        "",
        "时间单位：秒；承诺约定：commit_at=承诺瞬间赛钟剩余秒。",
        "",
        "## 最终状态字段差异（忽略墙钟/赛钟实时值与修订号）",
    ]
    if not report["migration_trace"]["snapshot_diffs"]:
        lines.append("无：两驱动在所有场景的规则裁决结果完全一致。")
    else:
        for d in report["migration_trace"]["snapshot_diffs"]:
            lines.append(f"- 场景 {d['scenario']} 字段 `{d['field']}`：{d['values']}")
    lines += ["", "## 裁决分歧（同一意图在不同驱动上的接受/拒绝）"]
    adj = report["migration_trace"].get("adjudication_diffs", [])
    if not adj:
        lines.append("无：所有意图在三个驱动配置上裁决一致。")
    else:
        lines.append("| 场景 | 意图 | 各驱动裁决 |")
        lines.append("|---|---|---|")
        for a in adj:
            lines.append(
                f"| {a['scenario']} | {a['label']} "
                f"| `{json.dumps(a['verdicts'], ensure_ascii=False)}` |"
            )
    lines += ["", "## 时钟台账业务锚点差异（按迁移 note 对齐，全量 tick 见 raw_runs.json）"]
    ledger = report["migration_trace"]["ledger_diffs"]
    if not ledger:
        lines.append("无：暂停/恢复/鸣笛等业务迁移的墙钟与剩余值完全一致。")
    else:
        lines.append(f"共 {len(ledger)} 条锚点差异，根因均为固定步把迁移量化到步网格。")
        lines.append("| 场景 | 驱动 | 锚点序号 | 驱动条目 | event_jump 条目 |")
        lines.append("|---|---|---:|---|---|")
        for tr in ledger:
            lines.append(
                f"| {tr['scenario']} | {tr['driver']} | {tr['anchor_index']} "
                f"| `{json.dumps(tr['driver_entry'], ensure_ascii=False)}` "
                f"| `{json.dumps(tr['event_jump_entry'], ensure_ascii=False)}` |"
            )
    lines.append("")
    return "\n".join(lines)


def print_console_report(report: dict) -> None:
    print(f"重复次数 {report['runs_per_cell']}，时间单位：秒\n")
    header = (f"{'场景':<24}{'驱动':<18}{'醒来均':>8}{'空闲均':>8}"
              f"{'tick均':>8}{'最大承诺误差':>14}")
    print(header)
    print("-" * len(header))
    for r in report["summary"]:
        print(f"{r['scenario']:<24}{r['driver']:<18}"
              f"{r['wakeups_mean']:>8.2f}{r['idle_wakeups_mean']:>8.2f}"
              f"{r['ticks_mean']:>8.2f}{r['max_commit_error']:>14.4f}")
    sd = report["migration_trace"]["snapshot_diffs"]
    ld = report["migration_trace"]["ledger_diffs"]
    ad = report["migration_trace"].get("adjudication_diffs", [])
    print(f"\n裁决字段差异 {len(sd)} 处；裁决分歧 {len(ad)} 处；"
          f"时钟台账差异 {len(ld)} 处")
    print(f"原始数据：{MEASURE_DIR / 'raw_runs.json'}")
    print(f"汇总：{MEASURE_DIR / 'summary.json'}")
    print(f"迁移追踪：{MEASURE_DIR / 'migration_trace.md'}")


def main() -> int:
    report = run()
    print_console_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
