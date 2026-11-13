"""界面对照验证：模拟前端按钮序列，核对球权变化与真实赛钟。

通过与 index.html 相同的 HTTP 命令接口驱动，验证：
- 控件前置条件（未开局/停表期间的动作被拒，失败不改修订号）；
- 进球后球权转换、回合推进、比分只来自事件链；
- 暂停冻结真实赛钟，恢复后续走；
- /driver 暴露的事件跳度量在暂停期间不增长。
"""
from __future__ import annotations

import json
import time
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8096"


def cmd(name: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(
        f"{BASE}/cmd/{name}",
        data=json.dumps(body or {}).encode(), method="POST",
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())


def state() -> dict:
    with urllib.request.urlopen(f"{BASE}/state", timeout=5) as r:
        return json.loads(r.read())


def driver() -> dict:
    with urllib.request.urlopen(f"{BASE}/driver", timeout=5) as r:
        return json.loads(r.read())


def check(cond: bool, label: str) -> None:
    print(("✓ " if cond else "✗ ") + label)
    assert cond, label


def main() -> int:
    # 前置：未开局进球被拒，修订号不动
    rev0 = state()["revision"]
    d = cmd("goal", {"team": "A"})
    check(not d["ok"] and d["decision"]["reason"] == "shot_requires_live",
          "未开局进球被内核拒绝（界面对应按钮禁用 + 失败横幅）")
    check(state()["revision"] == rev0, "被拒动作不推进修订号")

    cmd("start_match")
    d = cmd("start_period", {"first_possession": "A"})
    s = d["state"]
    check(s["phase"] == "LIVE" and s["possession"] == "A"
          and s["turn_id"] == 0, "开节后 A 控球，回合 T0")

    # 无球权方出手被拒
    d = cmd("goal", {"team": "B"})
    check(not d["ok"] and d["decision"]["reason"] == "team_without_possession",
          "无球权方 B 出手被拒，失败反馈回回合赛制面板")

    # A 进球：得分 + 球权转换 + 回合推进
    before = state()
    d = cmd("goal", {"team": "A"})
    s = d["state"]
    check(s["score"] == {"A": 2, "B": 0}, "进球 +2 进入事件链比分")
    check(s["possession"] == "B" and s["turn_id"] == 1,
          "进球后球权转 B、回合 T0→T1（内核驱动控件换权）")
    check(s["clock"]["remaining"] <= before["clock"]["remaining"],
          "赛钟随 LIVE 墙钟单调递减")

    # 暂停冻结真实赛钟
    cmd("pause", {"note": "official"})
    s = state()
    check(s["phase"] == "PAUSED" and s["clock"]["live"] is False, "暂停进入 PAUSED")
    frozen = s["clock"]["remaining"]
    drv1 = driver()
    time.sleep(1.5)
    s2 = state()
    drv2 = driver()
    check(abs(s2["clock"]["remaining"] - frozen) < 1e-9,
          f"暂停 1.5 秒真实赛钟冻结（{frozen} 不变）")
    check(drv2["ticks"] == drv1["ticks"],
          f"事件跳暂停期间零 tick（{drv1['ticks']}→{drv2['ticks']}）")

    # 停表期间出手被拒
    d = cmd("goal", {"team": "B"})
    check(not d["ok"] and d["decision"]["reason"] == "shot_requires_live",
          "停表期间出手被拒，不消耗回合")

    # 恢复后续走
    cmd("resume")
    r1 = state()["clock"]["remaining"]
    time.sleep(1.0)
    r2 = state()["clock"]["remaining"]
    check(r2 < r1, f"恢复后赛钟续走（{r1:.3f}→{r2:.3f}）")

    # 终态核对：driver 指标体现事件跳低开销
    drv = driver()
    check(drv["clock"] == "event_jump", "界面芯片显示 event_jump 调度方案")
    print(f"\n调度度量：{drv}")
    print("界面对照验证通过：控件由回合赛制内核驱动，失败回到面板反馈。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
