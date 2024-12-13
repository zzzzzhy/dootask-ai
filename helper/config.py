import os

# 服务启动端口
SERVER_PORT = int(os.environ.get('PORT', 5001))

# 清空上下文的命令
CLEAR_COMMANDS = [":clear", ":reset", ":restart", ":new", ":清空上下文", ":重置上下文", ":重启", ":重启对话"]

# AI结束对话的关键词
BYE_WORDS = [
    # 简体中文
    "再见", "拜拜", "退下", "告辞", "走了", "下次见", "回头见", "不打扰了", "谢谢再见", "辛苦了",
    
    # 繁体中文
    "再見", "拜拜", "告辭", "下次見", "回頭見", "不打擾了", "謝謝再見", "辛苦了",
    
    # 英语
    "goodbye", "bye", "bye bye", "see you", "see you later", "farewell", "take care", "have a nice day",
    "thanks bye", "good night", "catch you later", "until next time",
    
    # 日语
    "さようなら", "じゃあね", "バイバイ", "また会いましょう", "お疲れ様でした", "失礼します",
    "では", "またね", "お先に", "お疲れ", "お疲れ様", "失礼いたします",
    
    # 韩语
    "안녕히 계세요", "안녕", "잘 가", "다음에 봐요", "수고하셨습니다", "안녕히 가세요",
    "다음에 만나요", "잘 있어요", "수고했어요",
    
    # 德语
    "auf wiedersehen", "tschüss", "bis später", "bis bald", "mach's gut", "ciao",
    "servus", "ade", "lebewohl",
    
    # 法语
    "au revoir", "salut", "à bientôt", "à plus tard", "adieu", "bonne journée",
    "à la prochaine", "au plaisir",
    
    # 印度尼西亚语
    "selamat tinggal", "sampai jumpa", "dadah", "sampai ketemu lagi", "permisi",
    "terima kasih", "selamat jalan",
    
    # 俄语
    "до свидания", "пока", "прощай", "увидимся", "всего хорошего", "до встречи",
    "счастливо", "всего доброго"
]

# AI结束对话的标记
END_CONVERSATION_MARK = "<!--::END_CHAT::-->"

# 流式响应超时时间
STREAM_TIMEOUT = 300
