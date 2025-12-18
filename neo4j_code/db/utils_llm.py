# -*-coding: UTF-8 -*-
"""
    Author: haoxiaolin
    CreateTime: 2025/5/12 09:50
    Description: 
"""
from settings import config
from chat_model import OpenAI_APIChat

base_url = config.LlmConfig.base_url
key = config.LlmConfig.key
model_name = config.LlmConfig.model_name
mdl = OpenAI_APIChat(base_url=base_url, key=key, model_name=model_name)
