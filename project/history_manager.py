# -*- coding: utf-8 -*-
import os
import json
import time
import re
import shutil

# 历史记录根目录
HISTORY_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "history")
# 知识库配置文件路径（持久化用）
KNOWLEDGE_CONFIG = os.path.join(HISTORY_ROOT, "knowledge_config.json")

# 全局变量
_knowledge_list = []  # 全局知识库列表


def init_history_dir():
    """初始化历史记录根目录"""
    if not os.path.exists(HISTORY_ROOT):
        os.makedirs(HISTORY_ROOT, exist_ok=True)
    # 加载知识库配置
    load_knowledge_base()


def sanitize_topic(topic):
    """清理主题名，确保可以作为合法文件夹名（兼容中文）"""
    # 只保留中文、字母、数字和下划线
    sanitized = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9_]', '', topic)
    # 限制长度不超过20个字符
    return sanitized[:20] if sanitized else f"聊天_{int(time.time())}"


def create_topic_dir(topic):
    """创建主题文件夹，返回完整路径"""
    sanitized_topic = sanitize_topic(topic)
    topic_dir = os.path.join(HISTORY_ROOT, sanitized_topic)

    # 处理重名主题，添加数字后缀
    counter = 1
    while os.path.exists(topic_dir):
        topic_dir = os.path.join(HISTORY_ROOT, f"{sanitized_topic}_{counter}")
        counter += 1

    os.makedirs(topic_dir, exist_ok=True)
    return topic_dir


def save_chat_history(topic_dir, chat_history, used_pins=None):
    """
    保存聊天记录和使用的引脚列表到JSON文件
    :param topic_dir: 主题文件夹路径
    :param chat_history: 聊天记录列表
    :param used_pins: 当前使用的引脚列表
    """
    history_file = os.path.join(topic_dir, "chat_history.json")
    data = {
        "chat_history": chat_history,
        "last_used_pins": used_pins if used_pins else []
    }
    with open(history_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_chat_history(topic_dir):
    """
    加载指定主题的聊天记录和最后使用的引脚列表
    :return: (chat_history, last_used_pins)
    """
    history_file = os.path.join(topic_dir, "chat_history.json")
    if os.path.exists(history_file):
        with open(history_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return (
                data.get('chat_history', []),
                data.get('last_used_pins', [])
            )
    return [], []


def save_code(topic_dir, code):
    """保存代码文件，按时间戳命名"""
    timestamp = time.strftime("%Y%m%d_%H%M%S", time.localtime())
    code_file = os.path.join(topic_dir, f"code_{timestamp}.py")
    with open(code_file, 'w', encoding='utf-8') as f:
        f.write(code)
    return code_file


def get_all_topics():
    """获取所有历史主题列表（按创建时间倒序）"""
    if not os.path.exists(HISTORY_ROOT):
        return []

    topics = []
    for item in os.listdir(HISTORY_ROOT):
        item_path = os.path.join(HISTORY_ROOT, item)
        if os.path.isdir(item_path):
            # 获取文件夹创建时间
            create_time = os.path.getctime(item_path)
            topics.append((item, create_time))

    # 按创建时间倒序排序
    topics.sort(key=lambda x: x[1], reverse=True)
    return [topic[0] for topic in topics]


def get_topic_dir(topic_name):
    """根据主题名获取完整路径"""
    return os.path.join(HISTORY_ROOT, topic_name)


def get_latest_code(topic_dir):
    """获取主题下最新的代码文件内容"""
    code_files = [f for f in os.listdir(topic_dir) if f.startswith("code_") and f.endswith(".py")]
    if not code_files:
        return ""

    # 按文件名（时间戳）倒序排序
    code_files.sort(reverse=True)
    latest_code_file = os.path.join(topic_dir, code_files[0])

    with open(latest_code_file, 'r', encoding='utf-8') as f:
        return f.read()


def delete_topic(topic_name):
    """删除指定主题及其所有文件"""
    topic_dir = get_topic_dir(topic_name)
    if os.path.exists(topic_dir):
        shutil.rmtree(topic_dir)
        return True
    return False


def rename_topic(old_name, new_name):
    """
    重命名主题文件夹
    :param old_name: 旧主题名
    :param new_name: 新主题名
    :return: 实际的新主题名（自动处理重名和非法字符）
    """
    old_dir = get_topic_dir(old_name)
    if not os.path.exists(old_dir):
        raise ValueError(f"主题「{old_name}」不存在")

    # 清理新名字，过滤非法字符
    sanitized_new = sanitize_topic(new_name)
    if not sanitized_new:
        raise ValueError("对话名称不能为空")

    # 如果新名字和旧名字完全一样，直接返回
    if sanitized_new == old_name:
        return old_name

    # 处理重名情况，自动添加数字后缀
    new_dir = os.path.join(HISTORY_ROOT, sanitized_new)
    counter = 1
    while os.path.exists(new_dir):
        new_dir = os.path.join(HISTORY_ROOT, f"{sanitized_new}_{counter}")
        counter += 1

    # 重命名文件夹
    os.rename(old_dir, new_dir)

    # 返回实际的新名字（可能带后缀）
    return os.path.basename(new_dir)


# ------------------------------
# 知识库相关函数
# ------------------------------
def load_knowledge_base():
    """加载知识库配置，从持久化文件恢复"""
    global _knowledge_list
    if os.path.exists(KNOWLEDGE_CONFIG):
        try:
            with open(KNOWLEDGE_CONFIG, 'r', encoding='utf-8') as f:
                _knowledge_list = json.load(f)
        except:
            _knowledge_list = []
    else:
        _knowledge_list = []


def save_knowledge_base():
    """保存知识库配置到持久化文件"""
    with open(KNOWLEDGE_CONFIG, 'w', encoding='utf-8') as f:
        json.dump(_knowledge_list, f, ensure_ascii=False, indent=2)


def add_knowledge(file_name, content):
    """
    添加新的知识库
    :param file_name: 知识库文件名
    :param content: 知识库文本内容
    """
    global _knowledge_list
    # 如果已经存在同名的，先删除旧的
    for i, kb in enumerate(_knowledge_list):
        if kb['name'] == file_name:
            del _knowledge_list[i]
            break
    # 添加新的知识库
    kb_item = {
        "name": file_name,
        "content": content,
        "upload_time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    }
    _knowledge_list.append(kb_item)
    # 保存到文件
    save_knowledge_base()


def delete_knowledge(index):
    """
    删除指定索引的知识库
    :param index: 列表中的索引
    :return: 是否成功
    """
    global _knowledge_list
    if 0 <= index < len(_knowledge_list):
        del _knowledge_list[index]
        save_knowledge_base()
        return True
    return False


def get_all_knowledge_names():
    """获取所有知识库的名字，用于界面显示"""
    return [kb['name'] for kb in _knowledge_list]


def get_all_knowledge_content():
    """
    获取所有知识库的内容，拼接成字符串，用于发给AI
    :return: 拼接后的知识库内容，为空则返回空字符串
    """
    if not _knowledge_list:
        return ""
    content_list = []
    for kb in _knowledge_list:
        content_list.append(f"--- 全局知识库：{kb['name']} ---\n{kb['content']}")
    return "\n\n".join(content_list)