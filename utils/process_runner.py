# -*- coding: utf-8 -*-
"""
进程运行工具 - 统一的子进程执行、流式消费与进程树级联终止

1. 解决 Windows 管道缓冲区塞满导致的死锁；
2. 解决 `subprocess.run(stdout=PIPE)` 与 `communicate(timeout)` 轮询导致的死锁；
3. 解决取消或超时后遗留僵尸子进程树的问题。
"""

from __future__ import annotations

import os
import platform
import queue
import subprocess
import threading
import time
from typing import Callable, List, Optional, Union

from base.LogManager import LogManager

logger = LogManager.get()


class ProcessRunnerTimeoutError(TimeoutError):
    """子进程运行超时"""


class ProcessRunnerCancelledError(RuntimeError):
    """子进程被外部取消"""


class ProcessRunner:
    """
    通用的子进程流式执行器。
    独立后台线程实时读取 stdout/stderr，防止管道缓冲区塞满死锁。
    支持超时与级联终止进程树。
    """

    def __init__(self) -> None:
        self.logger = logger

    def _get_creation_flags(self) -> int:
        if os.name != "nt":
            return 0
        # CREATE_NO_WINDOW 防止弹出黑色控制台窗口
        return subprocess.CREATE_NO_WINDOW

    def _start_new_session(self) -> bool:
        # Windows 下不支持 start_new_session，使用 CREATE_NEW_PROCESS_GROUP 替代
        if os.name == "nt":
            return False
        return True

    def _kill_process_tree(self, process: subprocess.Popen) -> None:
        """级联杀死整棵进程树，彻底清理子进程残留。"""
        if process.poll() is not None:
            return
        pid = process.pid
        try:
            if os.name == "nt":
                # 使用 taskkill /F /T 强制级联杀掉整棵进程树
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=self._get_creation_flags(),
                    check=False,
                )
            else:
                # Linux/macOS 使用 killpg 杀进程组
                try:
                    os.killpg(os.getpgid(pid), 15)  # SIGTERM
                    time.sleep(0.5)
                except Exception:
                    pass
                try:
                    os.killpg(os.getpgid(pid), 9)  # SIGKILL
                except Exception:
                    process.kill()
        except Exception as exc:
            self.logger.warning(f"级联终止进程树失败 (PID {pid}): {exc}")
            try:
                process.kill()
            except Exception:
                pass

    def run(
        self,
        command: List[str],
        cwd: Optional[str] = None,
        env: Optional[dict] = None,
        timeout: Optional[float] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
        output_callback: Optional[Callable[[str], None]] = None,
        input_text: Optional[str] = None,
    ) -> subprocess.CompletedProcess:
        """
        流式运行子进程。

        Args:
            command: 命令列表
            cwd: 工作目录
            env: 环境变量
            timeout: 超时时间（秒）
            cancel_check: 取消检查回调，返回 True 时立即终止
            output_callback: 输出回调，每读一行调用一次
            input_text: 启动时写入 stdin 的文本

        Returns:
            subprocess.CompletedProcess

        Raises:
            ProcessRunnerTimeoutError: 进程超时
            ProcessRunnerCancelledError: 进程被取消
        """
        command = [str(arg) for arg in command]
        env = env if env is not None else os.environ.copy()
        # 强制子进程输出使用非缓冲模式，确保实时读取
        if "PYTHONUNBUFFERED" not in env:
            env["PYTHONUNBUFFERED"] = "1"

        process = None
        try:
            kwargs = {}
            if os.name != "nt":
                kwargs["start_new_session"] = True

            process = subprocess.Popen(
                command,
                cwd=str(cwd) if cwd else None,
                env=env,
                stdin=subprocess.PIPE if input_text is not None else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=self._get_creation_flags(),
                **kwargs,
            )

            if input_text is not None and process.stdin is not None:
                try:
                    process.stdin.write(input_text)
                    process.stdin.close()
                except Exception:
                    pass

            lines: List[str] = []
            output_queue = queue.Queue()

            def read_output() -> None:
                """后台线程：持续流式消费子进程输出，防止管道阻塞"""
                if process.stdout is None:
                    output_queue.put(None)
                    return
                try:
                    for raw_line in process.stdout:
                        line = raw_line.rstrip()
                        lines.append(line)
                        if output_callback and line.strip():
                            try:
                                output_callback(line)
                            except Exception:
                                pass
                except Exception:
                    pass
                finally:
                    output_queue.put(None)

            read_thread = threading.Thread(target=read_output, daemon=True)
            read_thread.start()

            deadline = time.monotonic() + timeout if timeout else None

            # 主循环：监控取消、超时和进程结束
            while True:
                # 1. 检查取消
                if cancel_check is not None and cancel_check():
                    self.logger.info(f"子进程被取消，开始级联终止: {command[0]}")
                    self._kill_process_tree(process)
                    read_thread.join(timeout=1.0)
                    raise ProcessRunnerCancelledError(
                        f"子进程已被取消: {' '.join(command)}"
                    )

                # 2. 检查超时
                if deadline is not None and time.monotonic() >= deadline:
                    self.logger.warning(f"子进程超时，开始级联终止: {command[0]}")
                    self._kill_process_tree(process)
                    read_thread.join(timeout=1.0)
                    tail = "\n".join(lines[-10:]) if lines else ""
                    raise ProcessRunnerTimeoutError(
                        f"子进程超时（{timeout} 秒），最后输出：{tail}"
                    )

                # 3. 检查进程是否已退出
                returncode = process.poll()
                if returncode is not None:
                    # 等待读取线程结束，确保消费完所有输出
                    read_thread.join(timeout=2.0)
                    # 清理队列中剩余的 None 哨兵
                    while not output_queue.empty():
                        try:
                            output_queue.get_nowait()
                        except queue.Empty:
                            break
                    return subprocess.CompletedProcess(
                        command,
                        returncode,
                        "\n".join(lines),
                        None,
                    )

                # 4. 短暂休眠，避免空转消耗 CPU
                time.sleep(0.05)

        except (ProcessRunnerTimeoutError, ProcessRunnerCancelledError):
            raise
        except Exception as exc:
            self.logger.error(f"子进程执行异常: {exc}")
            if process is not None and process.poll() is None:
                self._kill_process_tree(process)
            raise RuntimeError(f"子进程执行失败: {exc}") from exc


# 全局单例，方便直接调用
_default_runner = ProcessRunner()


def run_process(
    command: List[str],
    cwd: Optional[str] = None,
    env: Optional[dict] = None,
    timeout: Optional[float] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
    output_callback: Optional[Callable[[str], None]] = None,
    input_text: Optional[str] = None,
) -> subprocess.CompletedProcess:
    """便捷入口：使用全局默认 ProcessRunner 运行子进程。"""
    return _default_runner.run(
        command,
        cwd=cwd,
        env=env,
        timeout=timeout,
        cancel_check=cancel_check,
        output_callback=output_callback,
        input_text=input_text,
    )
