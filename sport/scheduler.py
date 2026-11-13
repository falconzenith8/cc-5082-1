"""规则服务的时钟调度器：事件跳（选定方案）与旧版固定轮询并存。

- EventJumpScheduler：生产默认。非 LIVE 时无线程、零 tick；LIVE 时一个
  等待线程在“赛钟零点或外部命令唤醒”中较早者醒来，命令到达会主动唤醒，
  暂停后线程退出，恢复时重新拉起。
- FixedPollScheduler：旧接口兼容实现，保留原 50ms 固定轮询语义，
  客户端可用 --clock fixed 切回，行为与改造前完全一致。

两个调度器都只调用 RuleEngine.tick()，裁决内核没有分叉。
"""
from __future__ import annotations

import threading
import time
from typing import Optional

from .engine import RuleEngine
from .models import Phase


class ClockScheduler:
    name = "base"

    def __init__(self, engine: RuleEngine) -> None:
        self.engine = engine

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def on_command(self) -> None:
        """命令线程在调用引擎前后使用，用于唤醒可能在等待的调度线程。"""
        pass

    def metrics(self) -> dict:
        return {"name": self.name}


class FixedPollScheduler(ClockScheduler):
    """旧版固定轮询：每 interval 秒一次 tick，与改造前服务端等价。"""

    name = "fixed_poll"

    def __init__(self, engine: RuleEngine, interval: float = 0.05,
                 lock: threading.RLock | None = None) -> None:
        super().__init__(engine)
        self.interval = interval
        self._lock = lock or threading.RLock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.ticks = 0
        self.wakeups = 0

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            self.wakeups += 1
            with self._lock:
                self.engine.tick(time.monotonic())
            self.ticks += 1

    def on_command(self) -> None:
        # 旧版无需唤醒：下一个轮询周期自然会看到新状态
        pass

    def metrics(self) -> dict:
        return {"name": self.name, "interval": self.interval,
                "ticks": self.ticks, "wakeups": self.wakeups}


class EventJumpScheduler(ClockScheduler):
    """事件跳调度：只在赛钟零点或命令唤醒时醒来。

    线程仅在 LIVE 期间存活；pause/timeout/foul/鸣笛使阶段离开 LIVE 后，
    等待循环自行退出，直到下一次 resume/start_period 由命令线程重新拉起。
    引擎访问通过传入的锁串行化，调度线程绝不在持锁状态下阻塞等待，
    命令线程也不 join 调度线程，避免锁顺序死锁。
    """

    name = "event_jump"

    def __init__(self, engine: RuleEngine, lock: threading.RLock | None = None) -> None:
        super().__init__(engine)
        self._lock = lock or threading.RLock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._guard = threading.Lock()
        self.ticks = 0
        self.wakeups = 0
        self.idle_wakeups = 0
        self.command_signals = 0

    def start(self) -> None:
        # 开局前不是 LIVE，不起线程；等 start_period 命令拉起
        pass

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        with self._guard:
            t = self._thread
        if t and t is not threading.current_thread():
            t.join(timeout=1.0)

    def on_command(self) -> None:
        """命令线程钩子：唤醒等待者，并按需拉起 LIVE 线程（非阻塞）。"""
        self.command_signals += 1
        self._wake.set()
        self._ensure_live_thread()

    def _ensure_live_thread(self) -> None:
        with self._guard:
            if self._thread is not None and self._thread.is_alive():
                return
            with self._lock:
                phase = self.engine.fold().phase
            if phase is not Phase.LIVE:
                return
            self._wake.clear()
            self._thread = threading.Thread(
                target=self._run_live, name="event-jump-clock", daemon=True)
            self._thread.start()

    def _run_live(self) -> None:
        while not self._stop.is_set():
            with self._lock:
                st = self.engine.fold()
                phase = st.phase
                remaining = max(self.engine.clock.remaining, 0.0)
            if phase is not Phase.LIVE:
                return  # 停表/节间：线程退出，零 tick 零唤醒
            deadline = time.monotonic() + remaining
            # 等待期间不持锁；被命令提前唤醒时立即返回，由命令线程 tick
            self._wake.wait(remaining)
            if self._stop.is_set():
                return
            self.wakeups += 1
            now = time.monotonic()
            with self._lock:
                self.engine.tick(now)
            self.ticks += 1
            if now + 1e-6 >= deadline and not self._wake.is_set():
                self.idle_wakeups += 1  # 纯零点醒来（鸣笛），无外部命令
            self._wake.clear()
            with self._lock:
                phase = self.engine.fold().phase
            if phase is not Phase.LIVE:
                return

    def metrics(self) -> dict:
        alive = bool(self._thread and self._thread.is_alive())
        return {
            "name": self.name, "ticks": self.ticks, "wakeups": self.wakeups,
            "idle_wakeups": self.idle_wakeups,
            "command_signals": self.command_signals,
            "live_thread": alive,
        }
