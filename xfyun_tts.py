# xfyun_tts.py
import os
import json
import base64
import hashlib
import hmac
import websocket
import threading
import time
import ssl
from datetime import datetime
from time import mktime
from urllib.parse import urlencode
from wsgiref.handlers import format_date_time

class XFYunTTS:
    """讯飞语音合成核心模块"""
    
    def __init__(self, appid=None, api_key=None, api_secret=None):
        """
        初始化TTS模块
        :param appid: 讯飞APPID
        :param api_key: 讯飞API Key
        :param api_secret: 讯飞API Secret
        """
        self.appid = appid
        self.api_key = api_key
        self.api_secret = api_secret
        self.temp_dir = "tts_temp"
        self._init_dirs()

    def _init_dirs(self):
        """初始化临时目录"""
        os.makedirs(self.temp_dir, exist_ok=True)

    def _generate_ws_url(self):
        """生成WebSocket连接URL"""
        url = "wss://tts-api.xfyun.cn/v2/tts"
        now = datetime.now()
        date = format_date_time(mktime(now.timetuple()))

        signature_origin = f"host: ws-api.xfyun.cn\ndate: {date}\nGET /v2/tts HTTP/1.1"
        signature_sha = hmac.new(
            self.api_secret.encode(),
            signature_origin.encode(),
            digestmod=hashlib.sha256
        ).digest()
        signature_sha = base64.b64encode(signature_sha).decode()

        authorization_origin = (
            f'api_key="{self.api_key}", algorithm="hmac-sha256", '
            f'headers="host date request-line", signature="{signature_sha}"'
        )
        authorization = base64.b64encode(authorization_origin.encode()).decode()

        return f"{url}?{urlencode({
            'authorization': authorization,
            'date': date,
            'host': 'ws-api.xfyun.cn'
        })}"

    def _generate_audio_file(self, text, timeout=10):
        """
        生成语音文件
        :param text: 要合成的文本
        :param timeout: 超时时间（秒）
        :return: (音频文件路径, 错误信息)
        """
        if not all([self.appid, self.api_key, self.api_secret]):
            return None, "Missing API credentials"

        audio_file = os.path.join(self.temp_dir, f"tts_{int(time.time())}.pcm")
        websocket.enableTrace(False)

        def on_message(ws, message):
            try:
                msg = json.loads(message)
                if msg["code"] != 0:
                    raise Exception(msg["message"])
                audio = base64.b64decode(msg["data"]["audio"])
                with open(audio_file, "ab") as f:
                    f.write(audio)
                if msg["data"]["status"] == 2:
                    ws.close()
            except Exception as e:
                self.last_error = str(e)

        def on_error(ws, error):
            self.last_error = str(error)

        ws = websocket.WebSocketApp(
            self._generate_ws_url(),
            on_message=on_message,
            on_error=on_error
        )

        data = {
            "common": {"app_id": self.appid},
            "business": {
                "aue": "raw",
                "auf": "audio/L16;rate=16000",
                "vcn": "xiaoyan",
                "tte": "utf8"
            },
            "data": {
                "status": 2,
                "text": str(base64.b64encode(text.encode()), "UTF8")
            }
        }

        self.last_error = None
        thread = threading.Thread(target=lambda: ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE}))
        thread.start()

        # 发送数据
        ws.send(json.dumps(data))

        # 等待线程完成或超时
        thread.join(timeout)

        if not os.path.exists(audio_file) or os.path.getsize(audio_file) == 0:
            return None, self.last_error or "生成语音超时"

        return audio_file, None

    def text_to_speech(self, text, timeout=10):
        """
        文本转语音
        :param text: 要合成的文本（不超过300字）
        :param timeout: 超时时间（秒）
        :return: (音频文件路径, 错误信息)
        """
        if len(text) > 300:
            return None, "文本过长（最大300字）"
        
        return self._generate_audio_file(text, timeout)

    def cleanup(self):
        """清理临时文件"""
        for f in os.listdir(self.temp_dir):
            os.remove(os.path.join(self.temp_dir, f))
