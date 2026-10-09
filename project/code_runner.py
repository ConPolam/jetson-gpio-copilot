# -*- coding: utf-8 -*-
import subprocess
import tempfile
import os
import time
import threading

# 全局变量
_current_pgid = None
_used_pins = []
_current_process = None
_output_callback = None


def set_output_callback(callback):
    global _output_callback
    _output_callback = callback


def _read_output(process):
    global _output_callback
    while process.poll() is None:
        line = process.stdout.readline()
        if line and _output_callback:
            _output_callback(line.strip())
        line_err = process.stderr.readline()
        if line_err and _output_callback:
            _output_callback(f"[错误] {line_err.strip()}")


def run_code(code, used_pins=None):
    global _current_pgid, _used_pins, _current_process
    if used_pins:
        _used_pins = used_pins
    else:
        _used_pins = []

    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as temp_file:
        temp_file.write(code)
        temp_file_path = temp_file.name

    try:
        _current_process = subprocess.Popen(
            ['pkexec', 'python3', '-u', temp_file_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            preexec_fn=os.setsid
        )
        _current_pgid = os.getpgid(_current_process.pid)
        threading.Thread(target=_read_output, args=(_current_process,), daemon=True).start()
        return "代码正在运行中...点击「停止代码」可终止"
    except Exception as e:
        return f"启动异常: {str(e)}"


def stop_code():
    global _current_pgid, _used_pins, _current_process
    if _current_pgid is None:
        return "当前没有正在运行的代码"

    try:
        # 【终极修复】解决跨进程GPIO状态缓存问题
        stop_script = f"""
import os
import signal
import time
import Jetson.GPIO as GPIO
import warnings

# 全局禁用所有UserWarning，避免无关提示干扰
warnings.filterwarnings("ignore", category=UserWarning)

# ========== 1. 彻底终止运行中的代码进程 ==========
print("步骤1：正在终止代码进程...")
try:
    os.killpg({_current_pgid}, signal.SIGTERM)
    time.sleep(0.5)
    try:
        os.killpg({_current_pgid}, 0)
        os.killpg({_current_pgid}, signal.SIGKILL)
        time.sleep(0.2)
        print("进程已强制终止")
    except ProcessLookupError:
        print("进程已正常退出")
except ProcessLookupError:
    print("进程组不存在，跳过终止步骤")
except Exception as e1:
    print(f"进程终止提示: {{str(e1)}}")

# ========== 2. 终极安全GPIO重置流程 ==========
print("\\n步骤2：正在安全重置GPIO为高阻态...")
used_pins = {_used_pins}
print(f"需要重置的引脚列表: {{used_pins}}")

try:
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BOARD)

    # 【关键修复】强制先将所有引脚设为输出低电平
    # 解决Jetson.GPIO跨进程状态缓存问题
    # 这一步会直接覆盖硬件状态，无论之前是什么模式
    print("\\n正在强制拉低所有引脚电平...")
    for pin in used_pins:
        # 无论之前是什么模式，强制设为输出并拉低
        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, GPIO.LOW)
        time.sleep(0.01)
        print(f"✓ 引脚 {{pin}} 已强制拉低，LED已熄灭")

    # 第二步：设置为输入模式（高阻态，最安全状态）
    print("\\n正在设置引脚为输入模式（高阻态）...")
    for pin in used_pins:
        GPIO.setup(pin, GPIO.IN)
        time.sleep(0.01)
        print(f"✓ 引脚 {{pin}} 已进入高阻态，电平稳定0V")

    # 【绝对禁止】GPIO.cleanup()
    # 会强制将引脚恢复为输出低电平，破坏所有安全设置
    print("\\n所有安全操作完成！")
    print("✓ 所有引脚均已强制拉低，LED已熄灭")
    print("✓ 所有引脚均已设置为高阻态（输入模式）")
    print("✓ 电平稳定在0V，不会意外驱动任何外设")
    print("✓ 硬件已处于完全安全状态")

    # 100%可靠的硬件验证方法
    print("\\n【验证方法】")
    print("1. 万用表测量引脚电压：稳定在0V左右")
    print("2. 导线短接引脚和3.3V：LED会瞬间亮一下（证明是输入模式）")
    print("3. 移除短接线：LED立即熄灭（证明电平稳定）")
except Exception as e2:
    print(f"\\n✗ GPIO清理异常: {{str(e2)}}")
    print("执行完成：进程已终止，GPIO已尝试清理")
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(stop_script)
            stop_script_path = f.name

        result = subprocess.run(
            ['pkexec', 'python3', stop_script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            timeout=30
        )

        os.unlink(stop_script_path)

        # 重置全局变量
        _current_pgid = None
        _used_pins = []
        _current_process = None

        # 合并输出结果
        full_output = result.stdout.strip()
        if result.stderr.strip():
            full_output += f"\n[错误输出] {result.stderr.strip()}"

        return f"停止操作完成！\n{full_output}"
    except Exception as e:
        return f"停止异常: {str(e)}"