"""HTTP 服务端：承载规则内核，公布带修订号的状态。

所有命令在单把锁内串行执行；后台线程按墙钟 tick，有效时钟归零自动鸣笛。
客户端只能通过命令改变比赛，无法直接编辑比分。
"""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .engine import RuleEngine
from .models import EType, MatchConfig, Team
from .scheduler import ClockScheduler, EventJumpScheduler, FixedPollScheduler

STATIC_DIR = Path(__file__).parent / "static"


class GameServer:
    def __init__(self, cfg: MatchConfig | None = None,
                 clock: str = "event_jump", poll_interval: float = 0.05) -> None:
        self.lock = threading.RLock()
        self.engine = RuleEngine(cfg or MatchConfig(), wall_now=time.monotonic())
        self._stop = threading.Event()
        # clock="event_jump" 为选定方案；clock="fixed_poll" 保留旧版
        # 50ms 固定轮询语义，旧客户端可无缝切回。调度器共用服务端锁，
        # 保证 tick 与命令在同一串行队列里裁决。
        if clock == "fixed_poll":
            self.scheduler: ClockScheduler = FixedPollScheduler(
                self.engine, interval=poll_interval, lock=self.lock)
        elif clock == "event_jump":
            self.scheduler = EventJumpScheduler(self.engine, lock=self.lock)
        else:
            raise ValueError(f"未知时钟调度方案: {clock}")
        self.clock_name = clock

    def start(self) -> None:
        self.scheduler.start()

    def stop(self) -> None:
        self._stop.set()
        self.scheduler.stop()

    def command(self, name: str, body: dict) -> dict:
        with self.lock:
            self.scheduler.on_command()
            self.engine.tick(time.monotonic())
            eng = self.engine
            team = Team(body["team"]) if body.get("team") else None
            if name == "start_match":
                d = eng.start_match(Team(body.get("first_possession", "A")))
            elif name == "start_period":
                d = eng.start_period(Team(body.get("first_possession", "A")))
            elif name == "pause":
                d = eng.pause(body.get("note", "client_pause"))
            elif name == "resume":
                d = eng.resume()
            elif name == "timeout":
                d = eng.timeout(team)
            elif name == "possession":
                d = eng.possession(team)
            elif name == "goal":
                d = eng.goal(team, body.get("points"))
            elif name == "shot_miss":
                d = eng.shot_miss(team)
            elif name == "foul":
                d = eng.foul(team)
            elif name == "free_throw":
                d = eng.free_throw(team, body["foul_id"], bool(body.get("made")))
            elif name == "revoke":
                d = eng.revoke(body["event_id"], body.get("reason", "review"))
            elif name == "inject":
                d = eng.inject(
                    EType(body["event_type"]), team, int(body["period"]),
                    int(body["turn_id"]), float(body["commit_at"]),
                    body.get("payload") or {},
                )
            else:
                return {"ok": False, "error": "unknown_command"}
            # 命令可能改变阶段（start_period/resume/撤销犯规回到 LIVE），
            # 执行后再通知一次，事件跳调度器据此按需拉起等待线程
            self.scheduler.on_command()
            return {
                "ok": d.accepted,
                "decision": d.to_dict(),
                "state": eng.snapshot(),
            }

    def state(self) -> dict:
        with self.lock:
            self.engine.tick(time.monotonic())
            return self.engine.snapshot()

    def audit(self, kind: str) -> list[dict]:
        with self.lock:
            if kind == "events":
                return self.engine.audit_events()
            if kind == "decisions":
                return self.engine.audit_decisions()
            if kind == "clock":
                return self.engine.audit_clock()
            return []


class Handler(BaseHTTPRequestHandler):
    server_version = "CircuitBall/1.0"

    def _json(self, code: int, payload) -> None:
        data = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        game: GameServer = self.server.game
        if self.path in ("/", "/index.html"):
            return self._serve_static("index.html", "text/html; charset=utf-8")
        if self.path == "/state":
            return self._json(200, game.state())
        if self.path.startswith("/audit/"):
            return self._json(200, game.audit(self.path.rsplit("/", 1)[-1]))
        if self.path == "/config":
            with game.lock:
                return self._json(200, game.engine.cfg.to_dict())
        if self.path == "/driver":
            with game.lock:
                payload = game.scheduler.metrics()
                payload["clock"] = game.clock_name
                return self._json(200, payload)
        self._json(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        game: GameServer = self.server.game
        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self._json(400, {"ok": False, "error": "bad_json"})
        if not self.path.startswith("/cmd/"):
            return self._json(404, {"error": "not_found"})
        name = self.path[len("/cmd/"):]
        try:
            result = game.command(name, body)
        except KeyError as exc:
            return self._json(400, {"ok": False, "error": f"missing_field:{exc}"})
        except ValueError as exc:
            return self._json(400, {"ok": False, "error": str(exc)})
        self._json(200 if result.get("ok") else 409, result)

    def _serve_static(self, name: str, ctype: str) -> None:
        path = STATIC_DIR / name
        if not path.exists():
            return self._json(404, {"error": "not_found"})
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args) -> None:  # 安静日志
        return


def make_server(host: str = "127.0.0.1", port: int = 8077,
                cfg: MatchConfig | None = None,
                clock: str = "event_jump") -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.game = GameServer(cfg, clock=clock)
    httpd.game.start()
    return httpd


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Circuit Ball rule server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8077)
    parser.add_argument("--quarter-seconds", type=float, default=60.0)
    parser.add_argument("--ot-seconds", type=float, default=30.0)
    parser.add_argument(
        "--clock", choices=["event_jump", "fixed_poll"], default="event_jump",
        help="时钟推进方案：event_jump（选定，按期限跳跃）或 "
             "fixed_poll（旧版 50ms 固定轮询，兼容回退）",
    )
    args = parser.parse_args()
    cfg = MatchConfig(
        quarter_seconds=args.quarter_seconds,
        ot_seconds=args.ot_seconds,
    )
    httpd = make_server(args.host, args.port, cfg, clock=args.clock)
    print(f"Circuit Ball on http://{args.host}:{args.port} (clock={args.clock})")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.game.stop()
        httpd.server_close()


if __name__ == "__main__":
    main()
