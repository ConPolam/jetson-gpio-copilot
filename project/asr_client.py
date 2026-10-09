# -*- coding: utf-8 -*-
import base64
import time
import hashlib
import hmac
import json
import pyaudio
import threading
import wave
import uuid
import websocket
from urllib.parse import quote
import datetime
from config import IFLYTEK_APPID, IFLYTEK_APIKEY, IFLYTEK_APISECRET

# 音频参数，讯飞要求：16k 16bit 单声道 PCM
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
CHUNK = 1024


class IFlytekASR:
    def __init__(self, on_result=None, on_error=None):
        self.appid = IFLYTEK_APPID
        self.api_key = IFLYTEK_APIKEY
        self.api_secret = IFLYTEK_APISECRET
        self.on_result = on_result
        self.on_error = on_error
        # 状态标志
        self.is_running = False
        self.stop_flag = False
        self.final_result = ""
        # 音频相关
        self.pa = None
        self.stream = None
        self.frames = []
        # 本地会话标记
        self.local_session_id = None

    def _create_auth_url(self):
        """生成讯飞新版WebAPI的鉴权WebSocket URL（官方标准实现）"""
        host = "iat-api.xfyun.cn"  # 修正：正确的接口域名
        path = "/v2/iat"

        # 生成RFC1123格式的UTC时间
        now = datetime.datetime.now(datetime.timezone.utc)
        date = now.strftime('%a, %d %b %Y %H:%M:%S GMT')

        # 构造签名原始字符串（官方标准格式）
        signature_origin = f"host: {host}\ndate: {date}\nGET {path} HTTP/1.1"

        # HMAC-SHA256加密生成签名（官方标准算法）
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            signature_origin.encode('utf-8'),
            digestmod=hashlib.sha256
        ).digest()
        signature = base64.b64encode(signature).decode('utf-8')

        # 构造Authorization头
        authorization_origin = f'api_key="{self.api_key}", algorithm="hmac-sha256", headers="host date request-line", signature="{signature}"'
        authorization = base64.b64encode(authorization_origin.encode('utf-8')).decode('utf-8')

        # 构造最终的WebSocket连接URL
        url = f"wss://{host}{path}?authorization={quote(authorization)}&date={quote(date)}&host={quote(host)}"
        return url

    def _ws_recognize(self, audio_data):
        """新版WebSocket接口的语音识别（官方标准实现）"""
        try:
            # 校验必要参数
            if not self.appid or not self.api_key or not self.api_secret:
                err_msg = "APPID/APIKey/APISecret 不能为空，请在 config.py 中正确配置"
                if self.on_error:
                    self.on_error(err_msg)
                return err_msg

            # 检查音频长度，讯飞听写最大支持60秒音频
            audio_length = len(audio_data) / (2 * RATE)  # 16bit=2字节，16k采样率
            if audio_length > 60:
                err_msg = f"录音过长，最大支持60秒，当前录音{round(audio_length, 1)}秒，请缩短录音时间"
                if self.on_error:
                    self.on_error(err_msg)
                return err_msg

            # 生成鉴权URL并连接WebSocket
            ws_url = self._create_auth_url()
            print(f"[DEBUG] 连接地址: {ws_url}")

            ws = websocket.WebSocket()
            ws.connect(ws_url, timeout=30)
            print("[DEBUG] WebSocket连接成功")

            # 构造请求数据，一次性发送全部音频
            audio_base64 = base64.b64encode(audio_data).decode('utf-8')
            request_data = {
                "common": {"app_id": self.appid},
                "business": {
                    "language": "zh_cn",
                    "domain": "iat",
                    "accent": "mandarin",
                    "vad_eos": 10000,  # 整数类型，单位毫秒
                    "sample_rate": "16000"  #string类型，必须是string类型
                },
                "data": {
                    "status": 2,  # status=2表示这是最后一帧数据，一次性发送全部音频
                    "format": "audio/L16;rate=16000",
                    "encoding": "raw",
                    "audio": audio_base64
                }
            }

            # 发送音频数据
            ws.send(json.dumps(request_data))
            print("[DEBUG] 已发送音频数据")

            # 接收识别结果
            final_text = ""
            while True:
                result = ws.recv()
                if not result:
                    break
                print(f"[DEBUG] 接口返回: {result}")

                try:
                    result_json = json.loads(result)
                except json.JSONDecodeError as e:
                    err_msg = f"接口返回数据解析失败: {str(e)}"
                    if self.on_error:
                        self.on_error(err_msg)
                    ws.close()
                    return err_msg

                code = result_json.get("code", 0)
                # 处理接口返回的错误
                if code != 0:
                    err_msg = f"识别失败 (code={code}): {result_json.get('message', '未知错误')}"
                    if self.on_error:
                        self.on_error(err_msg)
                    ws.close()
                    return err_msg

                # 解析识别文本（官方标准解析方式）
                if "data" in result_json and "result" in result_json["data"]:
                    result_data = result_json["data"]["result"]
                    if "ws" in result_data:
                        for ws_item in result_data["ws"]:
                            for cw_item in ws_item["cw"]:
                                final_text += cw_item["w"]

                # 识别完成，退出循环
                if result_json["data"]["status"] == 2:
                    break

            ws.close()
            print(f"[DEBUG] 最终识别结果: {final_text}")
            return final_text

        except Exception as e:
            import traceback
            traceback.print_exc()
            err_msg = f"请求处理异常: {str(e)}"
            if self.on_error:
                self.on_error(err_msg)
            return err_msg

    def start(self):
        """启动语音识别，开始录音"""
        if self.is_running:
            return False
        self.stop_flag = False
        self.final_result = ""
        self.frames = []
        self.is_running = True
        # 初始化 pyaudio，打开麦克风
        try:
            self.pa = pyaudio.PyAudio()
            self.stream = self.pa.open(
                format=FORMAT,
                channels=CHANNELS,
                rate=RATE,
                input=True,
                frames_per_buffer=CHUNK
            )
        except Exception as e:
            err_msg = f"打开麦克风失败: {str(e)}"
            if self.on_error:
                self.on_error(err_msg)
            self.is_running = False
            return False

        # 启动录音线程
        def record_thread():
            while not self.stop_flag:
                try:
                    chunk = self.stream.read(CHUNK, exception_on_overflow=False)
                    self.frames.append(chunk)
                    time.sleep(0.001)  # 主动让出 CPU
                except Exception:
                    break

        threading.Thread(target=record_thread, daemon=True).start()
        return True

    def stop(self):
        """停止录音，并调用接口识别"""
        if not self.is_running:
            return ""
        self.stop_flag = True
        time.sleep(0.3)  # 等待最后一部分音频写入
        # 保存调试录音（可选）
        if self.frames:
            try:
                wav_path = "asr_debug_record.wav"
                wf = wave.open(wav_path, 'wb')
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(self.pa.get_sample_size(FORMAT))
                wf.setframerate(RATE)
                wf.writeframes(b''.join(self.frames))
                wf.close()
                print(f"[INFO] 调试录音已保存至 {wav_path}")
            except Exception as e:
                print(f"[WARN] 保存调试录音失败: {e}")
        # 关闭音频资源
        if self.stream:
            try:
                self.stream.stop_stream()
                self.stream.close()
            except Exception:
                pass
        if self.pa:
            try:
                self.pa.terminate()
            except Exception:
                pass
        # 如果没有录到任何音频，直接返回
        if not self.frames:
            err_msg = "未录制到任何音频数据"
            if self.on_error:
                self.on_error(err_msg)
            self.is_running = False
            return err_msg
        # 生成本地会话 ID（用于日志）
        self.local_session_id = uuid.uuid4().hex

        # 在后台线程中进行识别，避免阻塞界面
        def recognize_thread():
            audio_data = b''.join(self.frames)
            result = self._ws_recognize(audio_data)
            self.final_result = result
            if self.on_result:
                self.on_result(result)
            self.is_running = False

        threading.Thread(target=recognize_thread, daemon=True).start()
        return self.final_result