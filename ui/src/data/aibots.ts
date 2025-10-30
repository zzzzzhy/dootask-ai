export type AIBotKey =
  | "openai"
  | "claude"
  | "deepseek"
  | "gemini"
  | "grok"
  | "ollama"
  | "zhipu"
  | "qianwen"
  | "wenxin"

export interface AIBotItem {
  value: AIBotKey
  label: string
  src: string
  desc: string
  tags: string[]
  tagLabel?: string
}

export const AIBotList: AIBotItem[] = [
  {
    value: "openai",
    label: "ChatGPT",
    src: "/ai/ui/avatars/openai.png",
    desc: "我是一个人工智能助手，为用户提供问题解答和指导。我没有具体的身份，只是一个程序。您有什么问题可以问我哦？",
    tags: [],
  },
  {
    value: "claude",
    label: "Claude",
    src: "/ai/ui/avatars/claude.png",
    desc: "我是 Claude，由 Anthropic 公司创造出来的 AI 助手机器人。我的工作是帮助人类，与人对话并给出解答。",
    tags: [],
  },
  {
    value: "deepseek",
    label: "DeepSeek",
    src: "/ai/ui/avatars/deepseek.png",
    desc: "DeepSeek 大语言模型算法是北京深度求索人工智能基础技术研究有限公司推出的深度合成服务算法。",
    tags: [],
  },
  {
    value: "gemini",
    label: "Gemini",
    src: "/ai/ui/avatars/gemini.png",
    desc: "我是由 Google 开发的生成式人工智能聊天机器人。它基于同名的 Gemini 系列大型语言模型，是应对 ChatGPT 崛起而开发的。",
    tags: [],
  },
  {
    value: "grok",
    label: "Grok",
    src: "/ai/ui/avatars/grok.png",
    desc: "Grok 是由 xAI 开发的生成式人工智能聊天机器人，旨在通过实时回答用户问题来提供帮助。",
    tags: [],
  },
  {
    value: "ollama",
    label: "Ollama",
    src: "/ai/ui/avatars/ollama.png",
    desc: "Ollama 是一个轻量级、可扩展的框架，旨在让用户能够在本地机器上构建和运行大型语言模型。",
    tags: [],
  },
  {
    value: "zhipu",
    label: "智谱清言",
    src: "/ai/ui/avatars/zhipu.png",
    desc: "我是智谱清言，是智谱 AI 公司训练的语言模型。我的任务是针对用户的问题和要求提供适当的答复和支持。",
    tags: [],
  },
  {
    value: "qianwen",
    label: "通义千问",
    src: "/ai/ui/avatars/qianwen.png",
    desc: "我是达摩院自主研发的超大规模语言模型，能够回答问题、创作文字，还能表达观点、撰写代码。",
    tags: [],
  },
  {
    value: "wenxin",
    label: "文心一言",
    src: "/ai/ui/avatars/wenxin.png",
    desc: "我是文心一言，英文名是 ERNIE Bot。我能够与人对话互动，回答问题，协助创作，高效便捷地帮助人们获取信息、知识和灵感。",
    tags: [],
  },
]
