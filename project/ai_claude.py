# -*- coding: utf-8 -*-
import requests
import json
import re
import urllib3
import os
import base64
from docx import Document
from config import *
import history_manager

# 按照官方文档，彻底关闭SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 单文件最大限制：10MB，避免prompt溢出
MAX_FILE_SIZE = 10 * 1024 * 1024


def _extract_text_from_txt(file_path):
    """提取TXT文件内容，兼容中文编码"""
    encodings = ['utf-8', 'gbk', 'gb2312', 'utf-16']
    for enc in encodings:
        try:
            with open(file_path, 'r', encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    raise ValueError("TXT文件编码识别失败，请尝试另存为UTF-8格式")


def _extract_text_from_docx(file_path):
    """提取DOCX文件内容"""
    doc = Document(file_path)
    full_text = []
    for para in doc.paragraphs:
        if para.text.strip():
            full_text.append(para.text)
    return '\n'.join(full_text)


def _encode_image_to_base64(file_path):
    """将图片编码为Base64字符串"""
    with open(file_path, 'rb') as f:
        return base64.b64encode(f.read()).decode('utf-8')


def process_file(file_path):
    """通用文件处理函数，返回（内容类型, 处理后内容），带文件大小校验"""
    # 校验文件大小
    file_size = os.path.getsize(file_path)
    if file_size > MAX_FILE_SIZE:
        raise ValueError(f"文件过大，最大支持10MB，当前文件大小：{round(file_size / 1024 / 1024, 2)}MB")

    ext = os.path.splitext(file_path)[1].lower()
    if ext == '.txt':
        return 'text', _extract_text_from_txt(file_path)
    elif ext == '.docx':
        return 'text', _extract_text_from_docx(file_path)
    elif ext in ['.jpg', '.jpeg']:
        return 'image', _encode_image_to_base64(file_path)
    else:
        raise ValueError(f"不支持的文件类型：{ext}，仅支持 .txt, .docx, .jpg, .jpeg")


def _fix_json_newlines(json_str):
    """
    修复JSON字符串中未转义的换行符问题
    这是Claude API最常见的JSON格式错误
    """
    # 匹配所有双引号包裹的字符串
    pattern = re.compile(r'"([^"\\]*(?:\\.[^"\\]*)*)"', re.DOTALL)

    def replace_newlines(match):
        # 将字符串内部的换行符替换为转义的\n
        string_content = match.group(1)
        fixed_content = string_content.replace('\n', '\\n').replace('\r', '\\r')
        return f'"{fixed_content}"'

    return pattern.sub(replace_newlines, json_str)


def call_claude(user_input=None, file_path=None, conversation_history=None):
    # 【修复1】强制补全指令：仅上传文件无文本时，补充默认指令，确保AI遵循格式
    if not user_input or user_input.strip() == "":
        user_input = "请基于我上传的文件内容，严格按照系统提示词的要求，生成Jetson Nano对应的控制代码，并只返回指定格式的JSON，不要额外说明文字"

    # 初始化历史记录
    if conversation_history is None:
        conversation_history = []

    # 构建当前输入内容
    current_content = []
    file_info_text = ""
    file_name = ""

    # 处理文件
    if file_path:
        file_name = os.path.basename(file_path)
        file_type, file_content = process_file(file_path)
        if file_type == 'text':
            # 文本文件：直接拼接到输入，强化格式约束
            file_info_text = f"\n\n【用户上传的文件：{file_name}，文件内容如下】\n{file_content}\n【文件内容结束】\n请严格基于上述内容，按照系统提示词的要求返回指定格式的JSON，不要额外内容"
        elif file_type == 'image':
            # 【修复2】严格对齐OpenAI多模态格式，确保中转API兼容
            current_content.append({
                "type": "text",
                "text": f"{SYSTEM_PROMPT}\n用户现在的问题是：{user_input}\n用户上传了图片：{file_name}，请识别图片中的内容，严格按照系统提示词要求返回指定格式的JSON"
            })
            current_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{file_content}"
                }
            })

    # 【注入知识库内容】获取全局知识库，作为最高优先级要求
    knowledge_content = history_manager.get_all_knowledge_content()

    # 【修复3】系统提示词强注入，无论是否有历史对话，都确保格式约束生效
    if not current_content:
        # 纯文本模式（文本/文档）
        full_text = f"""{SYSTEM_PROMPT}
"""
        # 注入知识库内容，最高优先级
        if knowledge_content:
            full_text += f"""
【全局AI知识库要求（最高优先级）】
以下是全局的知识库内容，你必须100%严格遵守这些要求，所有的回答、代码生成都要基于这些内容，这比任何用户的临时指令优先级都要高：
{knowledge_content}

"""
        # 拼接历史对话
        for msg in conversation_history:
            if msg['sender'] == '用户':
                full_text += f"用户: {msg['text']}\n"
            elif msg['sender'] == 'AI':
                full_text += f"你: {msg['text']}\n"
        # 拼接用户当前输入
        full_text += f"用户现在的问题是：{user_input}{file_info_text}\n请严格只返回符合要求的JSON格式内容，不要任何额外的解释、说明、问候语，确保JSON字符串中没有未转义的换行符"

        messages = [{"role": "user", "content": full_text}]
    else:
        # 多模态模式（图片），也要注入知识库内容
        text_part = f"{SYSTEM_PROMPT}\n"
        if knowledge_content:
            text_part += f"""
【全局AI知识库要求（最高优先级）】
以下是全局的知识库内容，你必须100%严格遵守这些要求，所有的回答、代码生成都要基于这些内容，这比任何用户的临时指令优先级都要高：
{knowledge_content}

"""
        text_part += f"用户现在的问题是：{user_input}\n用户上传了图片：{file_name}，请识别图片中的内容，严格按照系统提示词要求返回指定格式的JSON，确保JSON字符串中没有未转义的换行符"
        # 替换原来的text部分，加入知识库
        current_content[0]['text'] = text_part
        messages = [{"role": "user", "content": current_content}]

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "model": MODEL_NAME,
        "messages": messages,
        "max_tokens": 2048,
        "temperature": 0.2,
        "response_format": {"type": "json_object"}  # 【修复4】强制API返回JSON格式，OpenAI标准参数
    }

    try:
        response = requests.post(API_BASE_URL, headers=headers, json=data, timeout=120, verify=False)
        response.raise_for_status()
        result = response.json()
        ai_text = result['choices'][0]['message']['content']

        # 【修复5】新增调试日志，打印AI原始回复，方便定位问题
        print("=" * 50)
        print("AI原始返回内容：")
        print(ai_text)
        print("=" * 50)

        # 【修复6】增强JSON提取容错机制，多层级匹配
        json_str = None
        # 1. 优先匹配代码块里的JSON
        code_match = re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', ai_text, re.IGNORECASE)
        if code_match:
            json_str = code_match.group(1).strip()
        else:
            # 2. 匹配完整的JSON对象（支持换行、嵌套）
            json_match = re.search(r'\{[\s\S]*\}', ai_text)
            if not json_match:
                raise ValueError(f"AI 回复格式错误，未找到 JSON 结构，AI原始回复：{ai_text[:200]}...")
            json_str = json_match.group(0).strip()

        # 【关键修复】修复JSON中未转义的换行符问题
        json_str = _fix_json_newlines(json_str)

        # 打印修复后的JSON，方便调试
        print("修复后的JSON内容：")
        print(json_str)
        print("=" * 50)

        # 解析JSON
        parsed = json.loads(json_str)

        # 过滤 emoji，防止 Tkinter 报错
        def remove_emoji(text):
            if not text:
                return ""
            emoji_pattern = re.compile("["
                                       u"\U0001F600-\U0001F64F"
                                       u"\U0001F300-\U0001F5FF"
                                       u"\U0001F680-\U0001F6FF"
                                       u"\U0001F1E0-\U0001F1FF"
                                       "]+", flags=re.UNICODE)
            return emoji_pattern.sub(r'', text)

        if 'chat_message' in parsed:
            parsed['chat_message'] = remove_emoji(parsed['chat_message'])
        if 'chat_topic' in parsed:
            parsed['chat_topic'] = remove_emoji(parsed['chat_topic'])

        return parsed
    except requests.exceptions.RequestException as e:
        raise Exception(f"AI未接通，请重试: {str(e)}")
    except json.JSONDecodeError as e:
        raise Exception(f"JSON解析失败: {str(e)}，AI原始返回内容：{ai_text[:500]}...")
    except Exception as e:
        raise Exception(f"处理失败: {str(e)}")