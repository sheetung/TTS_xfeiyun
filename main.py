# plugin.py
from pkg.plugin.context import register, handler, BasePlugin, EventContext,APIHost
from pkg.plugin.events import *
from pkg.core.content import MessageChain, Voice
from .xfyun_tts import XFYunTTS
import json
import os
import base64

# CONFIG_PATH = "config.json"

@register(name="TTS_xfeiyun", description="Langbot讯飞语音合成插件", version="0.1", author="sheetung")
class XFyunTTSPlugin(BasePlugin):
    def __init__(self, host: APIHost):
        super().__init__(host)
        self.config = self._load_config()
        self.cur_dir = os.path.dirname(__file__)
        self.cfg_dir = os.path.join(self.cur_dir, 'config.json')
        # 提取语音合成参数
        business_params = {
            k: v for k, v in self.config.items()
            if k in ["aue", "auf", "vcn", "tte", "speed", "volume", "pitch"]
        }
        
        self.tts_client = XFYunTTS(
            appid=self.config.get("APPID"),
            api_key=self.config.get("APIKey"),
            api_secret=self.config.get("APISecret"),
            **business_params
        )

    def _load_config(self):
        """加载配置文件"""
        if os.path.exists(self.cfg_dir):
            with open(self.cfg_dir, "r") as f:
                return json.load(f)
        return {}

    def _save_config(self):
        """保存配置文件"""
        with open(self.cfg_dir, "w") as f:
            json.dump(self.config, f, indent=2)

    @handler(PersonNormalMessageReceived)
    @handler(GroupNormalMessageReceived)
    async def handle_message(self, ctx: EventContext):
        msg = ctx.event.text_message.strip()
        sender_id = ctx.event.sender_id

        # 处理API密钥配置
        if msg.startswith("/apicfg "):
            parts = msg[len("/apicfg "):].split("&")
            if len(parts) != 3:
                ctx.add_return("reply", ["格式错误，正确格式：/apicfg APPID&APIKey&APISecret"])
                ctx.prevent_default()
                return
                
            self.config.update(zip(
                ["APPID", "APIKey", "APISecret"],
                [p.strip() for p in parts]
            ))
            self._save_config()
            
            # 重新初始化TTS客户端
            business_params = {
                k: v for k, v in self.config.items()
                if k in ["aue", "auf", "vcn", "tte", "speed", "volume", "pitch"]
            }
            self.tts_client = XFYunTTS(
                appid=self.config["APPID"],
                api_key=self.config["APIKey"],
                api_secret=self.config["APISecret"],
                **business_params
            )
            
            ctx.add_return("reply", ["API配置更新成功！"])
            ctx.prevent_default()
            return

        # 处理语音合成参数配置
        elif msg.startswith("/ttscfg "):
            args = msg[len("/ttscfg "):].strip()
            if not args:
                ctx.add_return("reply", ["格式：/ttscfg 参数=值&参数=值（支持参数：vcn, speed, volume, pitch, aue, auf, tte）"])
                ctx.prevent_default()
                return

            params = {}
            valid_params = ["vcn", "speed", "volume", "pitch", "aue", "auf", "tte"]
            
            for pair in args.split("&"):
                if "=" not in pair:
                    ctx.add_return("reply", [f"无效参数格式：{pair}"])
                    ctx.prevent_default()
                    return
                    
                key, value = pair.split("=", 1)
                key = key.strip().lower()
                
                if key not in valid_params:
                    ctx.add_return("reply", [f"无效参数：{key}"])
                    ctx.prevent_default()
                    return
                
                # 验证数值型参数
                if key in ["speed", "volume", "pitch"]:
                    if not value.isdigit() or not 0 <= int(value) <= 100:
                        ctx.add_return("reply", [f"{key}参数需为0-100整数"])
                        ctx.prevent_default()
                        return
                    value = int(value)
                
                params[key] = value

            # 更新配置并保存
            self.config.update(params)
            self._save_config()
            
            # 重新初始化TTS客户端
            business_params = {
                k: v for k, v in self.config.items()
                if k in ["aue", "auf", "vcn", "tte", "speed", "volume", "pitch"]
            }
            self.tts_client = XFYunTTS(
                appid=self.config.get("APPID"),
                api_key=self.config.get("APIKey"),
                api_secret=self.config.get("APISecret"),
                **business_params
            )
            
            ctx.add_return("reply", ["语音参数更新成功！"])
            ctx.prevent_default()
            return

        # 处理TTS请求
        if msg.startswith("/tts "):
            text = msg[4:].strip()
            if not text:
                ctx.add_return("reply", ["请输入要合成的文本，例如：/tts 你好"])
                ctx.prevent_default()
                return

            ctx.prevent_default()
            ctx.host.start_typing()

            try:
                audio_path, error = self.tts_client.text_to_speech(text)
                if error:
                    ctx.add_return("reply", [error])
                    return

                # 发送语音消息
                with open(audio_path, "rb") as f:
                    base64_audio = base64.b64encode(f.read()).decode()
                
                message_chain = MessageChain([Voice(base64=base64_audio)])
                await ctx.reply(message_chain)

                # 清理临时文件
                os.remove(audio_path)
            except Exception as e:
                self.ap.logger.error(f"语音合成异常: {str(e)}")
                ctx.add_return("reply", ["语音合成失败，请稍后重试"])

    def __del__(self):
        self.tts_client.cleanup()
