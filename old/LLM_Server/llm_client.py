import logging
from abc import ABC
from openai import OpenAI
import openai
import os
import httpx
import requests
import json
import time
import uuid
import hmac
import hashlib
import base64
import logging
from typing import Optional, AsyncGenerator
from openai import OpenAI, AsyncOpenAI

"""
同步非流式/同步流式/异步非流式/异步流式：
- sync_nonstream_chat
- sync_stream_chat
- async_nonstream_chat
- async_stream_chat
"""

class LlmConfig:
    # IP_PORT = "https://192.168.100.121:8880"
    # base_url = IP_PORT + "/v1"
    # key = "EMPTY"
    # model_name = "QwQ-32B"

    # test
    IP_PORT = "https://192.168.100.121:8880"
    # IP_PORT = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    key = "sk-f9f3209599454a49ba6fb4f36c3c0434" 
    model_name = "deepseek-v3"
    # base_url = "https://api.deepseek.com"
    # key = "sk-b362bcbd376944eabb02b037d61e62f3"
    # model_name = "deepseek-chat"

    APPID = ""
    SecretKey = ""
    USERID = "5"

    TOKEN = ""
    TOKEN_WG = None
    TMP_TEST_DIGEST = ""

base_url = LlmConfig.base_url
api_key = LlmConfig.key
IP_PORT = LlmConfig.IP_PORT
APPID = LlmConfig.APPID
USERID = LlmConfig.USERID
SecretKey = LlmConfig.SecretKey
TOKEN_WG = LlmConfig.TOKEN_WG
TMP_TEST_DIGEST = LlmConfig.TMP_TEST_DIGEST

class LLMHeader(object):

    @staticmethod
    def decode_jwt_payload(token):
        try:
            parts = token.split(".")
            if len(parts) != 3:
                raise ValueError("不是标准的 JWT 格式，应为三段用 . 分隔")

            payload_b64 = parts[1]
            missing_padding = len(payload_b64) % 4
            if missing_padding == 1:
                raise ValueError("非法的 Base64 编码，长度对4取模为1")
            elif missing_padding:
                payload_b64 += "=" * (4 - missing_padding)

            payload_json = base64.urlsafe_b64decode(payload_b64).decode("utf-8")
            return json.loads(payload_json)

        except (Exception) as e:
            logging.error(f"解析 token 失败: {e}")
            return None

    # 创建会话
    @staticmethod
    def create_session(gw_url, app_id: str, user_id: str, secret_key: str):
        # request_id是16字节的UUID
        request_id = uuid.uuid4().hex[:16]
        # hmac.new() 要求 key 参数必须是 bytes 或 bytearray 类型，而不能直接使用字符串
        secret_key_bytes = secret_key.encode("utf-8")

        request_str = app_id + user_id + request_id
        request_str_bytes = request_str.encode("utf-8")
        hmac_digest = hmac.new(secret_key_bytes, request_str_bytes, hashlib.sha256).digest()
        digest = base64.b64encode(hmac_digest).decode("utf-8")

        # 临时和注销对应的测试
        TMP_TEST_DIGEST = digest

        data = {
            "appId": app_id,
            "userId": user_id,
            "requestId": request_id,
            "digest": digest,
        }

        # 加了调网关会出现传参错误
        # data = json.dumps(data)

        response = requests.post(gw_url, json=data, verify=False)
        response_data = response.json()
        logging.info("创建会话响应:", response_data)

        code = response_data.get("code")
        message = response_data.get("message")
        if code == "0":
            token = response_data.get("data").get("token")
            global TOKEN_WG
            TOKEN_WG = token
            print(TOKEN_WG)
            return True, message
        else:
            logging.error("创建LLM会话失败，错误信息:", message)
            return False, message

    # 获取header
    def get_session_header(self, gw_ip_port, app_id, user_id, secret_key: str):
        create_session_url = gw_ip_port + "/session/createSession"

        status, token, message, headers = False, None, None, None
        if TOKEN_WG is None:
            status, message = self.create_session(
                create_session_url, app_id, user_id, secret_key
            )

            if not status:
                logging.error("创建会话失败：", message)
                return None, message

        token = TOKEN_WG
        token_payload = self.decode_jwt_payload(token)
        if not token_payload:
            logging.error("无法解析 token，当前token值：", token)
            return None, "无法解析token"

        exp = token_payload.get("exp")
        if exp < int(time.time()):
            logging.info("token已过期，重新创建会话")
            status, message = self.create_session(
                create_session_url, app_id, user_id, secret_key
            )
            if not status:
                logging.error("token已过期，重新创建会话时失败，错误码:", message)
                return None, message

        # 每次的request_id都是随机值
        secret_key_bytes = secret_key.encode("utf-8")
        request_id = uuid.uuid4().hex[:64]
        print("request_id:" + request_id)
        request_id_bytes = request_id.encode("utf-8")
        hmac_digest = hmac.new(secret_key_bytes, request_id_bytes, hashlib.sha256).digest()
        # print("生成的digest字节码:", hmac_digest)
        digest = base64.b64encode(hmac_digest).decode("utf-8")
        # print("解析后的digest字节码:", base64.b64decode(digest))

        # 构建M-Gateway-Request
        data = {"requestId": request_id, "digest": digest}
        # 可能也需要去掉，需要测试
        data = json.dumps(data).encode("utf-8")
        headers = {
            "M-Gateway-Token": TOKEN_WG,
            "M-Gateway-Request": base64.b64encode(data).decode("utf-8"),
        }
        print("获取到的headers:", headers)
        return headers


class LLMClient(object):

    def __init__(self, *args):
        self.base_url = base_url
        self.api_key = api_key
        # headers = LLMHeader().get_session_header(
        #     gw_ip_port=IP_PORT,
        #     app_id=APPID,
        #     user_id=USERID,
        #     secret_key=SecretKey,
        # )

        # 初始化同步客户端
        self.client = OpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=60.0,
            max_retries=1,
            # http_client=httpx.Client(verify=False),
            # default_headers=headers
        )
        # 初始化异步客户端
        self.async_client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=60.0,
            max_retries=3,
            # http_client=httpx.AsyncClient(verify=False),
            # default_headers=headers
        )

    def sync_nonstream_chat(self, prompt: str, model: str, max_tokens: int = 40000, temperature: float = 0.7, system_prompt: Optional[str] = None) -> str:
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content
        except Exception as e:
            logging.getLogger(__name__).error(f"未知错误: {e}")
            raise

    def sync_stream_chat(self, prompt: str, model: str, max_tokens: int = 40000, temperature: float = 0.7, system_prompt: Optional[str] = None):
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
            for chunk in response:
                content = chunk.choices[0].delta.content
                if content:
                    yield content
        except Exception as e:
            logging.getLogger(__name__).error(f"流式调用错误: {e}")
            raise

    async def async_nonstream_chat(self, prompt: str, model: str, max_tokens: int = 40000, temperature: float = 0.7, system_prompt: Optional[str] = None) -> str:
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            response = await self.async_client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content
        except Exception as e:
            logging.getLogger(__name__).error(f"未知错误: {e}")
            raise

    async def async_stream_chat(self, prompt: str, model: str, max_tokens: int = 40000, temperature: float = 0.7, system_prompt: Optional[str] = None) -> AsyncGenerator[str, None]:
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            response = await self.async_client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
            async for chunk in response:
                content = chunk.choices[0].delta.content
                if content:
                    yield content
        except Exception as e:
            logging.getLogger(__name__).error(f"未知错误: {e}")
            raise