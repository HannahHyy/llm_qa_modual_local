# -*-coding: UTF-8 -*-
"""
    Author: haoxiaolin
    CreateTime: 2025/10/10 14:13
    Description: 
"""
from pydantic import BaseModel


class CreateSession(BaseModel):
    user_id: str
    session_name: str


class DeleteSession(BaseModel):
    user_id: str
    session_id: str


class AskQuestion(BaseModel):
    user_id: str
    session_id: str
    question: str
