import Jetson.GPIO as GPIO

# 这里填写你刚才测试用的引脚号，比如7
TEST_PIN = 7

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BOARD)

# 【关键修复】先setup引脚为输入模式（安全操作，不会改变原有高阻态）
GPIO.setup(TEST_PIN, GPIO.IN)

# 读取引脚当前的模式（返回数字值）
pin_mode = GPIO.gpio_function(TEST_PIN)

# 数字值映射
mode_map = {
    0: "输入模式（高阻态）✅",
    1: "输出模式 ❌"
}

# 读取引脚当前的电平
pin_level = GPIO.input(TEST_PIN)
level_map = {
    GPIO.HIGH: "高电平",
    GPIO.LOW: "低电平"
}

print(f"引脚 {TEST_PIN} 状态检测：")
print(f"当前模式：{mode_map.get(pin_mode, f'特殊功能模式（代码：{pin_mode}）')}")
print(f"当前电平：{level_map.get(pin_level, '未知电平')}")

# 高阻态验证
print("\n✅ 高阻态验证：用手触摸引脚，电平会在高低之间跳动")
print("按 Ctrl+C 退出")

try:
    while True:
        current_level = GPIO.input(TEST_PIN)
        print(f"实时电平：{current_level}", end="\r")
except KeyboardInterrupt:
    print("\n\n检测结束")
finally:
    GPIO.cleanup()