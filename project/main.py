# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import scrolledtext, filedialog, messagebox, simpledialog
import threading
import os
from ai_claude import call_claude, process_file
from code_runner import run_code, stop_code, set_output_callback
import Jetson.GPIO as GPIO
import history_manager
from asr_client import IFlytekASR


class JetsonAIAssistant:
    def __init__(self, root):
        self.root = root
        self.root.title("Jetson AI 嵌入式开发助手")
        self.root.geometry("1400x800")
        # 绑定窗口关闭事件
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        # 设置代码输出的回调
        set_output_callback(self.on_code_output)
        # 初始化历史记录
        history_manager.init_history_dir()
        # 当前聊天状态
        self.current_topic = None  # 当前聊天主题
        self.current_topic_dir = None  # 当前主题文件夹路径
        self.current_chat_history = []  # 当前聊天的历史记录
        self.current_code = ""
        self.current_used_pins = []
        # 布局：左（历史面板）-中（聊天区）-右（代码区）三栏
        self.paned_window = tk.PanedWindow(root, orient=tk.HORIZONTAL)
        self.paned_window.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        # 左侧：历史记录面板
        self.history_frame = tk.Frame(self.paned_window)
        self.paned_window.add(self.history_frame, width=200)
        self.history_label = tk.Label(self.history_frame, text="聊天历史", font=("Arial", 12, "bold"))
        self.history_label.pack(anchor=tk.W, padx=5, pady=5)
        # 新增：AI知识库按钮
        self.knowledge_btn = tk.Button(self.history_frame, text="AI知识库", command=self.open_knowledge_manager,
                                       font=("Arial", 12), bg="#9C27B0", fg="white")
        self.knowledge_btn.pack(fill=tk.X, padx=5, pady=5)
        self.new_chat_btn = tk.Button(self.history_frame, text="新建聊天", command=self.on_new_chat,
                                      font=("Arial", 12), bg="#FF9800", fg="white")
        self.new_chat_btn.pack(fill=tk.X, padx=5, pady=5)
        # 新增：重命名对话按钮
        self.rename_chat_btn = tk.Button(self.history_frame, text="重命名对话", command=self.on_rename_chat,
                                         font=("Arial", 12), bg="#2196F3", fg="white")
        self.rename_chat_btn.pack(fill=tk.X, padx=5, pady=5)
        self.delete_chat_btn = tk.Button(self.history_frame, text="删除选中", command=self.on_delete_chat,
                                         font=("Arial", 12), bg="#f44336", fg="white")
        self.delete_chat_btn.pack(fill=tk.X, padx=5, pady=5)
        self.history_listbox = tk.Listbox(self.history_frame, font=("Arial", 11))
        self.history_listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.history_listbox.bind("<<ListboxSelect>>", self.on_select_history)
        # 加载历史主题
        self.load_history_topics()
        # 中间：聊天区
        self.chat_frame = tk.Frame(self.paned_window)
        self.paned_window.add(self.chat_frame, width=600)
        # 聊天记录区
        self.chat_area = scrolledtext.ScrolledText(self.chat_frame, wrap=tk.WORD, font=("Arial", 12))
        self.chat_area.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.chat_area.tag_config("blue", foreground="blue")
        self.chat_area.tag_config("green", foreground="green")
        self.chat_area.tag_config("red", foreground="red")
        self.chat_area.tag_config("gray", foreground="gray")
        self.chat_area.tag_config("black", foreground="black")
        self.chat_area.config(state=tk.DISABLED)
        # 输入区
        self.input_frame = tk.Frame(self.chat_frame)
        self.input_frame.pack(fill=tk.X, padx=5, pady=5)
        self.input_entry = tk.Entry(self.input_frame, font=("Arial", 12))
        self.input_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.input_entry.bind("<Return>", self.on_send)

        # 语音识别按钮
        self.asr_btn = tk.Button(self.input_frame, text="语音识别", command=self.on_asr_toggle,
                                 font=("Arial", 12), bg="#FF5722", fg="white")
        self.asr_btn.pack(side=tk.RIGHT, padx=5)

        self.send_doc_btn = tk.Button(self.input_frame, text="发送文档", command=self.on_send_document,
                                      font=("Arial", 12), bg="#2196F3", fg="white")
        self.send_doc_btn.pack(side=tk.RIGHT, padx=5)

        self.send_btn = tk.Button(self.input_frame, text="发送", command=self.on_send, font=("Arial", 12))
        self.send_btn.pack(side=tk.RIGHT, padx=5)
        # 右侧：代码区
        self.code_frame = tk.Frame(self.paned_window)
        self.paned_window.add(self.code_frame, width=600)
        self.code_label = tk.Label(self.code_frame, text="生成的代码：", font=("Arial", 12, "bold"))
        self.code_label.pack(anchor=tk.W, padx=5, pady=5)
        self.code_area = scrolledtext.ScrolledText(self.code_frame, wrap=tk.WORD, font=("Courier New", 11))
        self.code_area.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.btn_frame = tk.Frame(self.code_frame)
        self.btn_frame.pack(fill=tk.X, padx=5, pady=5)
        self.execute_btn = tk.Button(self.btn_frame, text="执行代码", command=self.on_execute, font=("Arial", 12),
                                     bg="#4CAF50", fg="white")
        self.execute_btn.pack(side=tk.LEFT, padx=5)
        self.stop_btn = tk.Button(self.btn_frame, text="停止代码", command=self.on_stop, font=("Arial", 12),
                                  bg="#f44336", fg="white")
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        # 初始化：系统提示
        self.add_chat_msg("系统",
                          "你好！我是嵌入式开发助手，可以实现零代码便携式嵌入式开发。\n1. 直接输入指令发送（例如：让引脚7的LED闪烁5次）\n2. 点击「发送文档」上传 .txt, .docx 或 .jpg/.jpeg 文件\n3. 左侧面板可管理AI知识库、新建/重命名/删除聊天",
                          "blue")

        # 语音识别相关状态
        self.asr_instance = None
        self.is_asr_running = False

    def load_history_topics(self):
        """加载所有历史主题到列表框"""
        self.history_listbox.delete(0, tk.END)
        topics = history_manager.get_all_topics()
        for topic in topics:
            self.history_listbox.insert(tk.END, topic)

    def on_new_chat(self):
        """新建聊天按钮回调"""
        # 重置当前聊天状态
        self.current_topic = None
        self.current_topic_dir = None
        self.current_chat_history = []
        self.current_code = ""
        self.current_used_pins = []
        # 清空聊天区和代码区
        self.chat_area.config(state=tk.NORMAL)
        self.chat_area.delete(1.0, tk.END)
        self.chat_area.config(state=tk.DISABLED)
        self.code_area.delete(1.0, tk.END)
        # 取消历史列表的选中状态
        self.history_listbox.selection_clear(0, tk.END)
        # 显示系统提示
        self.add_chat_msg("系统", "已创建新聊天，请输入你的指令", "blue")

    def on_rename_chat(self):
        """重命名对话按钮回调"""
        selection = self.history_listbox.curselection()
        if not selection:
            messagebox.showwarning("警告", "请先选择要重命名的聊天主题")
            return
        old_topic = self.history_listbox.get(selection[0])
        # 弹出输入对话框，默认值为旧名字，方便用户修改
        new_name = simpledialog.askstring(
            title="重命名对话",
            prompt="请输入新的对话名称：",
            initialvalue=old_topic,
            parent=self.root
        )
        # 用户点击取消，直接返回
        if new_name is None:
            return
        # 验证新名字非空
        new_name = new_name.strip()
        if not new_name:
            messagebox.showwarning("警告", "对话名称不能为空")
            return
        try:
            # 调用重命名函数
            new_topic = history_manager.rename_topic(old_topic, new_name)
            # 如果重命名的是当前正在使用的主题，更新当前状态
            if self.current_topic == old_topic:
                self.current_topic = new_topic
                self.current_topic_dir = history_manager.get_topic_dir(new_topic)
                self.add_chat_msg("系统", f"当前对话已重命名为：{new_topic}", "blue")
            # 刷新历史主题列表
            self.load_history_topics()
            # 自动选中新的主题，方便用户查看
            topics = history_manager.get_all_topics()
            if new_topic in topics:
                idx = topics.index(new_topic)
                self.history_listbox.selection_set(idx)
                self.history_listbox.see(idx)
            messagebox.showinfo("成功", f"对话已重命名为：{new_topic}")
        except Exception as e:
            messagebox.showerror("错误", f"重命名失败：{str(e)}")

    def on_delete_chat(self):
        """删除选中聊天按钮回调"""
        selection = self.history_listbox.curselection()
        if not selection:
            messagebox.showwarning("警告", "请先选择要删除的聊天主题")
            return
        topic_name = self.history_listbox.get(selection[0])
        if messagebox.askyesno("确认删除", f"确定要删除聊天主题「{topic_name}」吗？\n所有聊天记录和代码将被永久删除"):
            if history_manager.delete_topic(topic_name):
                # 如果删除的是当前聊天，重置状态
                if self.current_topic == topic_name:
                    self.on_new_chat()
                # 刷新历史列表
                self.load_history_topics()
                messagebox.showinfo("成功", f"聊天主题「{topic_name}」已删除")
            else:
                messagebox.showerror("错误", "删除失败，文件夹不存在")

    def on_select_history(self, event):
        """选择历史主题回调"""
        selection = self.history_listbox.curselection()
        if not selection:
            return
        topic_name = self.history_listbox.get(selection[0])
        topic_dir = history_manager.get_topic_dir(topic_name)
        # 加载聊天记录和最后使用的引脚列表
        chat_history, last_used_pins = history_manager.load_chat_history(topic_dir)
        latest_code = history_manager.get_latest_code(topic_dir)
        # 更新当前状态
        self.current_topic = topic_name
        self.current_topic_dir = topic_dir
        self.current_chat_history = chat_history
        self.current_code = latest_code
        self.current_used_pins = last_used_pins  # 关键修复：恢复使用的引脚列表
        # 清空并显示聊天记录
        self.chat_area.config(state=tk.NORMAL)
        self.chat_area.delete(1.0, tk.END)
        for msg in chat_history:
            self.add_chat_msg(msg['sender'], msg['text'], msg['color'], save=False)
        self.chat_area.config(state=tk.DISABLED)
        # 显示最新代码
        self.code_area.delete(1.0, tk.END)
        self.code_area.insert(tk.END, latest_code)
        self.add_chat_msg("系统", f"已加载历史聊天：{topic_name}\n已恢复使用的引脚列表：{last_used_pins}", "blue")

    def open_knowledge_manager(self):
        """打开AI知识库管理窗口"""
        # 创建模态窗口，阻塞主窗口
        kb_window = tk.Toplevel(self.root)
        kb_window.title("AI知识库管理")
        kb_window.geometry("500x400")
        kb_window.resizable(False, False)
        kb_window.grab_set()  # 模态，必须先关这个才能操作主窗口
        # 标题
        label = tk.Label(kb_window, text="全局AI知识库（所有对话自动应用这些要求）", font=("Arial", 12, "bold"))
        label.pack(padx=10, pady=10)
        # 知识库列表
        kb_listbox = tk.Listbox(kb_window, font=("Arial", 11), width=50, height=10)
        kb_listbox.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # 刷新列表函数
        def refresh_kb_list():
            kb_listbox.delete(0, tk.END)
            names = history_manager.get_all_knowledge_names()
            for name in names:
                kb_listbox.insert(tk.END, name)

        refresh_kb_list()
        # 按钮区
        btn_frame = tk.Frame(kb_window)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)

        # 添加知识库按钮
        def on_add_kb():
            # 文件选择，仅支持txt和docx
            file_types = [
                ("支持的知识库文件", "*.txt *.docx"),
                ("文本文件", "*.txt"),
                ("Word文档", "*.docx"),
                ("所有文件", "*.*")
            ]
            file_path = filedialog.askopenfilename(
                title="选择要添加的知识库文件",
                filetypes=file_types,
                parent=kb_window
            )
            if not file_path:
                return
            try:
                # 复用文件处理函数，解析内容
                file_type, content = process_file(file_path)
                file_name = os.path.basename(file_path)
                # 添加到全局知识库
                history_manager.add_knowledge(file_name, content)
                # 刷新列表
                refresh_kb_list()
                messagebox.showinfo("成功", f"知识库「{file_name}」添加成功！\n所有后续的AI对话都会自动应用这个知识库",
                                    parent=kb_window)
            except Exception as e:
                messagebox.showerror("错误", f"添加失败：{str(e)}", parent=kb_window)

        add_btn = tk.Button(btn_frame, text="添加知识库", command=on_add_kb,
                            font=("Arial", 12), bg="#4CAF50", fg="white")
        add_btn.pack(side=tk.LEFT, padx=5)

        # 删除知识库按钮
        def on_delete_kb():
            selection = kb_listbox.curselection()
            if not selection:
                messagebox.showwarning("警告", "请先选择要删除的知识库", parent=kb_window)
                return
            idx = selection[0]
            kb_name = kb_listbox.get(idx)
            if messagebox.askyesno("确认删除",
                                   f"确定要删除知识库「{kb_name}」吗？\n删除后将无法恢复，后续对话将不再应用这个知识库",
                                   parent=kb_window):
                # 修复：将错误的 delete_kb 改为正确的 delete_knowledge
                if history_manager.delete_knowledge(idx):
                    refresh_kb_list()
                    messagebox.showinfo("成功", f"知识库「{kb_name}」已删除", parent=kb_window)
                else:
                    messagebox.showerror("错误", "删除失败", parent=kb_window)

        delete_btn = tk.Button(btn_frame, text="删除知识库", command=on_delete_kb,
                               font=("Arial", 12), bg="#f44336", fg="white")
        delete_btn.pack(side=tk.LEFT, padx=5)
        # 关闭按钮
        close_btn = tk.Button(btn_frame, text="关闭", command=kb_window.destroy,
                              font=("Arial", 12))
        close_btn.pack(side=tk.RIGHT, padx=5)

    def add_chat_msg(self, sender, text, color, save=True):
        """添加聊天消息，可选是否保存到历史"""
        self.chat_area.config(state=tk.NORMAL)
        self.chat_area.insert(tk.END, f"[{sender}]: {text}\n\n", color)
        self.chat_area.see(tk.END)
        self.chat_area.config(state=tk.DISABLED)
        # 保存到当前聊天历史（系统消息不保存）
        if save and sender != "系统" and self.current_chat_history is not None:
            self.current_chat_history.append({
                "sender": sender,
                "text": text,
                "color": color
            })

    def on_code_output(self, text):
        """接收代码的实时输出，显示到聊天区"""
        self.root.after(0, self.add_chat_msg, "代码输出", text, "gray")

    def on_send(self, event=None):
        user_input = self.input_entry.get().strip()
        if not user_input:
            return
        self.add_chat_msg("用户", user_input, "black")
        self.input_entry.delete(0, tk.END)
        # 后台线程调用AI（纯文本）
        threading.Thread(target=self._ai_thread, args=(user_input, None), daemon=True).start()

    def on_send_document(self):
        """发送文档按钮的回调，支持先输入指令再上传文件"""
        # 先获取输入框里的指令
        user_input = self.input_entry.get().strip()
        self.input_entry.delete(0, tk.END)
        # 文件选择过滤器
        file_types = [
            ("支持的文件", "*.txt *.docx *.jpg *.jpeg"),
            ("文本文件", "*.txt"),
            ("Word文档", "*.docx"),
            ("图片文件", "*.jpg *.jpeg"),
            ("所有文件", "*.*")
        ]
        file_path = filedialog.askopenfilename(
            title="选择要发送的文件",
            filetypes=file_types
        )
        if not file_path:
            return  # 用户取消选择
        # 显示用户选择了文件
        file_name = os.path.basename(file_path)
        if user_input:
            show_msg = f"发送指令：{user_input}\n上传了文件：{file_name}"
        else:
            show_msg = f"上传了文件：{file_name}"
        self.add_chat_msg("用户", show_msg, "black")
        # 后台线程调用AI（带文件）
        threading.Thread(target=self._ai_thread, args=(user_input, file_path), daemon=True).start()

    def _ai_thread(self, user_input, file_path):
        try:
            result = call_claude(
                user_input=user_input,
                file_path=file_path,
                conversation_history=self.current_chat_history
            )
            self.root.after(0, self._on_ai_result, result)
        except Exception as e:
            self.root.after(0, self.add_chat_msg, "系统", f"AI调用失败: {str(e)}", "red")

    def _on_ai_result(self, result):
        chat_topic = result.get('chat_topic', '未命名聊天')
        chat_msg = result.get('chat_message', '')
        code = result.get('executable_code', '')
        hardware_config = result.get('hardware_config', {})
        used_pins = hardware_config.get('pins_used', [])
        # 如果是新聊天（还没有主题），创建主题文件夹
        if self.current_topic is None:
            self.current_topic = chat_topic
            self.current_topic_dir = history_manager.create_topic_dir(chat_topic)
            # 刷新历史主题列表
            self.root.after(0, self.load_history_topics)
            self.add_chat_msg("系统", f"已创建新聊天主题：{chat_topic}", "blue")
        # 显示AI回复
        self.add_chat_msg("AI", chat_msg, "green")
        # 显示代码
        self.code_area.delete(1.0, tk.END)
        self.code_area.insert(tk.END, code)
        self.current_code = code
        self.current_used_pins = used_pins
        # 保存聊天记录和代码，同时保存使用的引脚列表
        if self.current_topic_dir:
            history_manager.save_chat_history(
                self.current_topic_dir,
                self.current_chat_history,
                self.current_used_pins
            )
            history_manager.save_code(self.current_topic_dir, code)

    def on_execute(self):
        if not self.current_code:
            self.add_chat_msg("系统", "请先生成代码！", "red")
            return
        self.add_chat_msg("系统", f"正在执行代码...\n使用的引脚列表：{self.current_used_pins}", "blue")
        # 后台线程执行代码
        threading.Thread(target=self._execute_thread, daemon=True).start()

    def _execute_thread(self):
        try:
            result = run_code(self.current_code, self.current_used_pins)
            self.root.after(0, self._on_execute_result, result)
        except Exception as e:
            self.root.after(0, self._on_execute_result, f"执行异常: {str(e)}")

    def _on_execute_result(self, result):
        self.add_chat_msg("系统", f"执行结果:\n{result}", "blue")

    def on_stop(self):
        """停止代码按钮的回调"""
        self.add_chat_msg("系统", "正在停止代码...", "blue")
        result = stop_code()
        self.add_chat_msg("系统", result, "blue")

    def on_closing(self):
        """窗口关闭时的回调：复用stop_code()，避免重复弹窗"""
        self.add_chat_msg("系统", "正在清理GPIO并退出...", "blue")
        try:
            # 停止语音识别
            if self.is_asr_running and self.asr_instance:
                try:
                    self.asr_instance.stop()
                except:
                    pass
            # 复用stop_code()，和停止按钮逻辑一致，仅需1次密码
            stop_result = stop_code()
            self.add_chat_msg("系统", stop_result, "blue")
        except Exception as e:
            print(f"清理GPIO异常: {str(e)}")
        finally:
            # 关闭窗口
            self.root.destroy()

    def on_asr_toggle(self):
        """切换语音识别状态：启动/停止"""
        if not self.is_asr_running:
            # 启动语音识别
            self.start_asr()
        else:
            # 停止语音识别
            self.stop_asr()

    def start_asr(self):
        """启动语音识别"""
        try:
            # 更新按钮状态
            self.asr_btn.config(text="识别中", command=self.on_asr_toggle, bg="#f44336")
            self.is_asr_running = True

            # 定义回调
            def on_result(text):
                # 识别完成，在主线程更新UI
                self.root.after(0, self._asr_finish, text)

            def on_error(err):
                # 错误处理
                self.root.after(0, self._asr_error, err)

            # 创建ASR实例并启动
            self.asr_instance = IFlytekASR(on_result=on_result, on_error=on_error)
            if self.asr_instance.start():
                self.add_chat_msg("系统", "已开始语音识别，请说话，点击「识别中」按钮结束", "blue")
            else:
                self._asr_error("语音识别已在运行中")
        except Exception as e:
            self._asr_error(f"启动失败: {str(e)}")

    def stop_asr(self):
        """停止语音识别"""
        if self.asr_instance:
            self.asr_instance.stop()

    def _asr_finish(self, text):
        """语音识别完成，更新输入框"""
        # 恢复按钮状态
        self.asr_btn.config(text="语音识别", command=self.on_asr_toggle, bg="#FF5722")
        self.is_asr_running = False
        self.asr_instance = None

        # 过滤emoji，防止Tkinter报错
        def remove_emoji(t):
            if not t:
                return ""
            import re
            emoji_pattern = re.compile("["
                                       u"\U0001F600-\U0001F64F"
                                       u"\U0001F300-\U0001F5FF"
                                       u"\U0001F680-\U0001F6FF"
                                       u"\U0001F1E0-\U0001F1FF"
                                       "]+", flags=re.UNICODE)
            return emoji_pattern.sub(r'', t)

        clean_text = remove_emoji(text)
        if clean_text:
            # 将识别结果填入输入框
            self.input_entry.delete(0, tk.END)
            self.input_entry.insert(0, clean_text)
            self.add_chat_msg("系统", f"语音识别完成：{clean_text}", "green")
        else:
            self.add_chat_msg("系统", "未识别到有效语音内容", "gray")

    def _asr_error(self, err):
        """语音识别错误处理"""
        # 恢复按钮状态
        self.asr_btn.config(text="语音识别", command=self.on_asr_toggle, bg="#FF5722")
        self.is_asr_running = False
        self.asr_instance = None
        self.add_chat_msg("系统", f"语音识别出错：{err}", "red")


if __name__ == "__main__":
    root = tk.Tk()
    app = JetsonAIAssistant(root)
    root.mainloop()