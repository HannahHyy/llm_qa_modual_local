# -*-coding: UTF-8 -*-
"""
    Author: haoxiaolin
    CreateTime: 2025/10/9 16:30
    Description: 
"""
from loguru import logger


# 配置业务日志路由
def business_filter(business: str):
    def filter_func(record):
        return record["extra"].get("business") == business
    return filter_func


def exclude_event_filter(record):
    return record["extra"].get("business") != "event"


logger.add(
    "./logs/pro/fx_pro_{time:YYYY-MM-DD}.log",  # 文件名含日期
    rotation="500 MB",                 # 文件超过500MB时轮转
    retention="7 days",                # 保留7天日志
    compression="zip",                 # 压缩旧日志节省空间
    enqueue=True,                      # 多进程安全
    # filter=exclude_event_filter,
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}"
)


logger.add(
    "./logs/event/event_{time:YYYY-MM-DD}.log",
    rotation="200 MB",
    retention="30 days",
    filter=business_filter("event"),
)