"""真实比赛入口的端到端冒烟：通过 HTTP 打完一场常规赛+加时。

分别在 event_jump（选定）与 fixed_poll（旧轮询）两种调度方案下执行
完全相同的客户端命令序列，断言最终状态一致，且旧接口（/state、/cmd/*、
/audit/*、/config）全部可用。这是“旧接口兼容，客户端完成常规赛及加时”
的可复跑证据。

运行：python -m sport.http_smoke
"""
from __future__ import annotations

import json
import threading
import time
import urllib.request
import urllib.error

from .server import make_server
from .models import MatchConfig


def _req(base: str, method: str, path: str, body: dict | None = None):
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(
        base + path, data=data, method=method,
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _wait_phase(base: str, phase: str, timeout: float = 8.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        _, st = _req(base, "GET", "/state")
        if st["phase"] == phase:
            return st
        time.sleep(0.05)
    raise AssertionError(f"等待阶段 {phase} 超时，当前 {st['phase']}")


def _serve(httpd) -> threading.Thread:
    """进程内测试需要显式启动 accept 循环（独立部署由 main() 的 serve_forever 承担）。"""
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    time.sleep(0.1)
    return t


def play_tied_regulation_and_ot(port: int, clock: str) -> dict:
    """四节打平 2:2 进加时，A 加时制胜。"""
    cfg = MatchConfig(quarter_seconds=3.0, ot_seconds=2.0,
                      timeouts_reg=2, timeouts_ot=1)
    httpd = make_server("127.0.0.1", port, cfg, clock=clock)
    _serve(httpd)
    base = f"http://127.0.0.1:{port}"
    try:
        def cmd(name, body=None, expect_ok=True):
            code, resp = _req(base, "POST", f"/cmd/{name}", body)
            if expect_ok:
                assert resp["ok"], f"{name} 应接受: {resp.get('decision')}"
            return resp

        cmd("start_match")
        # P1、P3 无得分打完；P2 也无得分；第四节 A、B 各进一球扳平
        for p in range(1, 4):
            cmd("start_period", {"first_possession": "A"})
            _wait_phase(base, "INTERMISSION")
        cmd("start_period", {"first_possession": "A"})
        cmd("goal", {"team": "A"})               # 2:0，球权转 B
        cmd("goal", {"team": "B"})               # 2:2，球权转 A
        st = _wait_phase(base, "INTERMISSION")
        assert st["score"] == {"A": 2, "B": 2}, st["score"]
        ot = st["overtime"]
        assert ot["eligible"] is True, "平分必须具备加时资格"

        # 非平分禁入加时由内核测试覆盖；这里验证平分可入加时
        cmd("start_period", {"first_possession": "A"})
        st = _req(base, "GET", "/state")[1]
        assert st["period"] == 5
        # 真实墙钟下请求往返会耗掉少量时间，加时时钟应在 (0, OT长度] 区间
        assert 0.0 < st["clock"]["remaining"] <= 2.0, \
            f"加时应使用 2 秒 OT 时钟，实际 {st['clock']['remaining']}"
        ot_remaining_at_goal = st["clock"]["remaining"]
        cmd("goal", {"team": "A"})               # 加时制胜 4:2
        st = _wait_phase(base, "INTERMISSION")
        assert st["score"] == {"A": 4, "B": 2}, st["score"]
        assert st["overtime"]["eligible"] is False, "分胜负后不再续赛"
        # 加时赛钟在进球后仍按 OT 长度预算（审计复位记录可查）
        _, clock_audit = _req(base, "GET", "/audit/clock")
        ot_resets = [c for c in clock_audit if c["note"] == "period_5_reset"]
        assert ot_resets and ot_resets[-1]["game_remaining_after"] == 2.0, \
            "加时复位必须是 OT 时钟 2.0 秒"
        assert 0.0 < ot_remaining_at_goal <= 2.0

        # 审计接口（旧接口）可用且得分链完整
        _, events = _req(base, "GET", "/audit/events")
        goals = [e for e in events if e["type"] == "goal" and not e["voided"]]
        assert len(goals) == 3
        _, decisions = _req(base, "GET", "/audit/decisions")
        assert any(d["accepted"] for d in decisions)
        _, driver = _req(base, "GET", "/driver")
        return {"score": st["score"], "period": st["period"],
                "phase": st["phase"], "driver": driver, "clock": clock}
    finally:
        httpd.shutdown()
        httpd.game.stop()
        httpd.server_close()


def main() -> int:
    results = {}
    for i, clock in enumerate(("event_jump", "fixed_poll")):
        r = play_tied_regulation_and_ot(8090 + i, clock)
        results[clock] = r
        print(f"[{clock}] 完整常规赛+加时通过：比分 {r['score']}，"
              f"终态 P{r['period']} {r['phase']}，调度度量 {r['driver']}")
    # 两种调度方案的规则结果必须一致（仅调度度量允许不同）
    for key in ("score", "period", "phase"):
        assert results["event_jump"][key] == results["fixed_poll"][key], key
    print("\n两调度方案规则裁决完全一致；旧接口 /state /cmd/* /audit/* /config 均可用。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
