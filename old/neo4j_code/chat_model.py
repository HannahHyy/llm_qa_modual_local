# -*-coding: UTF-8 -*-
"""
    Author: haoxiaolin
    CreateTime: 2025/5/7 16:31
    Description:
"""

import logging
from abc import ABC
from openai import OpenAI
import openai
import os
import requests
import json
import time
import uuid
import hmac
import hashlib
import base64
from langchain_openai import ChatOpenAI

from settings import config

IP_PORT = config.LlmConfig.IP_PORT
APPID = config.LlmConfig.APPID
SecretKey = config.LlmConfig.SecretKey
USERID = config.LlmConfig.USERID

TOKEN = ""
TOKEN_WG = None
TMP_TEST_DIGEST = ""

LENGTH_NOTIFICATION_CN = "······\n由于模型支持的上下文长度的原因，回答被截断了"


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
def get_session_header(gw_ip_port, app_id, user_id, secret_key: str):
    create_session_url = gw_ip_port + "/session/createSession"

    status, token, message, headers = False, None, None, None
    if TOKEN_WG is None:
        status, message = create_session(
            create_session_url, app_id, user_id, secret_key
        )

        if not status:
            logging.error("创建会话失败：", message)
            return None, message

    token = TOKEN_WG
    token_payload = decode_jwt_payload(token)
    if not token_payload:
        logging.error("无法解析 token，当前token值：", token)
        return None, "无法解析token"

    exp = token_payload.get("exp")
    if exp < int(time.time()):
        logging.info("token已过期，重新创建会话")
        status, message = create_session(
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


class Base(ABC):
    def __init__(self, key, model_name, base_url):
        self.timeout = int(os.environ.get('LM_TIMEOUT_SECONDS', 600))
        self.key = key
        self.base_url = base_url

        self.model_name = model_name
        # headers = get_session_header(
        #     gw_ip_port=IP_PORT,
        #     app_id=APPID,
        #     user_id=USERID,
        #     secret_key=SecretKey,
        # )
        # client = OpenAI(
        #     api_key=self.key,
        #     base_url=self.base_url,
        #     default_headers=headers,
        #     http_client=httpx.Client(verify=False),
        #     max_retries=0,
        #     timeout=self.timeout
        # )
        self.client = OpenAI(api_key="sk-b362bcbd376944eabb02b037d61e62f3", base_url="https://api.deepseek.com")
        # self.client = ChatOpenAI(api_key="sk-b362bcbd376944eabb02b037d61e62f3", base_url="https://api.deepseek.com", model="deepseek-chat", temperature="0.4")

    def chat(self, system, history, gen_conf):
        if system:
            history.insert(0, {"role": "system", "content": system})
        try:
            response = self.client.chat.completions.create(
                # model=self.model_name,
                model="deepseek-chat",
                messages=history,
                **gen_conf)
            if any([not response.choices, not response.choices[0].message, not response.choices[0].message.content]):
                return "", 0
            ans = response.choices[0].message.content.strip()
            if response.choices[0].finish_reason == "length":
                ans += LENGTH_NOTIFICATION_CN

            # return ans, self.total_token_count(response)
            return ans
        except openai.APIError as e:
            logging.error("**ERROR**: " + str(e))
            return "**ERROR**: " + str(e), 0

    def chat_streamly(self, system, history, gen_conf):
        if system:
            history.insert(0, {"role": "system", "content": system})
        ans = ""

        try:
            response = self.client.chat.completions.create(
                # model=self.model_name,
                model="deepseek-chat",
                messages=history,
                stream=True,
                **gen_conf)
            for resp in response:
                if not resp.choices:
                    continue
                if not resp.choices[0].delta.content:
                    resp.choices[0].delta.content = ""

                ans = resp.choices[0].delta.content
                if resp.choices[0].finish_reason == "length":
                    ans = LENGTH_NOTIFICATION_CN

                # yield f"{json.dumps({'content': ans})}"
                yield f"{ans}"
            yield "done"

        except openai.APIError as e:
            yield ans + "\n**ERROR**: " + str(e)

    # 此处是chatOpenai的方法
    async def chat_streamly_cache(self, system, history, gen_conf, user_id, storage, session_id, *args):
        if system:
            history.insert(0, {"role": "system", "content": system})
        ans = ""
        reply_buffer = []
        try:
            response = self.client.stream(history, stream=True)
            for ans in response:
                ans = ans.content
                yield f"{ans}"
                reply_buffer.append(ans)
            yield "done"

        except openai.APIError as e:
            yield ans + "\n**ERROR**: " + str(e)

        finally:
            full_reply = "".join(reply_buffer).strip()
            print(full_reply)
            await storage.append_message(user_id=user_id, session_id=session_id, role="assistant", content=full_reply)

    def total_token_count(self, resp):
        try:
            return resp.usage.total_tokens
        except Exception:
            pass
        try:
            return resp["usage"]["total_tokens"]
        except Exception:
            pass
        return 0


class OpenAI_APIChat(Base):
    def __init__(self, key, model_name, base_url):
        if not base_url:
            raise ValueError("url cannot be None")
        model_name = model_name.split("___")[0]
        super().__init__(key, model_name, base_url)


class GPUStackChat(Base):
    def __init__(self, key=None, model_name="", base_url=""):
        if not base_url:
            raise ValueError("Local llm url cannot be None")
        if base_url.split("/")[-1] != "v1-openai":
            base_url = os.path.join(base_url, "v1-openai")
        super().__init__(key, model_name, base_url)


if __name__ == "__main__":
    print("\n==========开始获取请求头==========")

    mdl = OpenAI_APIChat(base_url=IP_PORT + "/v1/", key="EMPTY", model_name="QwQ-32B")
    m, tc = mdl.chat(None, [{"role": "user", "content": "Hello! How are you doing!"}], {"temperature": 0.9})
    print(m)