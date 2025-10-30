import type { AIBotKey } from "./aibots"

export type FieldControlType = "text" | "password" | "textarea" | "model"

export interface FieldConfig {
  label: string
  prop: string
  type?: FieldControlType
  placeholder?: string
  maxlength?: number
  showWordLimit?: number
  tip?: string
  tipPrefix?: string
  link?: string
  functions?: string
  sort?: number
}

export type ExtraFieldConfig = {
  prop: string
  after?: string
} & Partial<Omit<FieldConfig, "prop">>

export interface BotConfig {
  extraFields?: ExtraFieldConfig[]
}

interface SystemConfig {
  fields: FieldConfig[]
  aiList: Record<AIBotKey, BotConfig>
}

export const AISystemConfig: SystemConfig = {
  fields: [
    {
      label: "API Key",
      prop: "key",
      type: "password",
    },
    {
      label: "模型列表",
      prop: "models",
      type: "textarea",
      maxlength: 1000,
      showWordLimit: 0.9,
      placeholder: "一行一个模型名称",
      functions: "使用默认模型列表",
    },
    {
      label: "默认模型",
      prop: "model",
      type: "model",
      placeholder: "请选择默认模型",
      tip: "可选数据来自模型列表",
    },
    {
      label: "Base URL",
      prop: "base_url",
      placeholder: "Enter base URL...",
      tip: "API请求的基础URL路径，如果没有请留空",
    },
    {
      label: "使用代理",
      prop: "agency",
      placeholder: "支持 http 或 socks 代理",
      tip: "例如：http://proxy.com 或 socks5://proxy.com",
    },
    {
      label: "Temperature",
      prop: "temperature",
      placeholder: "模型温度，低则保守，高则多样",
      tip: "例如：0.7，范围：0-1，默认：0.7",
    },
    {
      label: "默认提示词",
      prop: "system",
      type: "textarea",
      maxlength: 20000,
      showWordLimit: 0.9,
      placeholder: "请输入默认提示词",
      tip: "例如：你是一个人开发的AI助手",
    },
  ],
  aiList: {
    openai: {
      extraFields: [
        {
          prop: "key",
          placeholder: "OpenAI API Key",
          link: "https://platform.openai.com/account/api-keys",
        },
        {
          prop: "models",
          link: "https://platform.openai.com/docs/models",
        },
      ],
    },
    claude: {
      extraFields: [
        {
          prop: "key",
          placeholder: "Claude API Key",
          link: "https://docs.anthropic.com/en/api/getting-started",
        },
        {
          prop: "models",
          link: "https://docs.anthropic.com/en/docs/about-claude/models",
        },
      ],
    },
    deepseek: {
      extraFields: [
        {
          prop: "key",
          placeholder: "DeepSeek API Key",
          link: "https://platform.deepseek.com/api_keys",
        },
        {
          prop: "models",
          link: "https://api-docs.deepseek.com/zh-cn/quick_start/pricing",
        },
      ],
    },
    gemini: {
      extraFields: [
        {
          prop: "key",
          placeholder: "Gemini API Key",
          link: "https://makersuite.google.com/app/apikey",
        },
        {
          prop: "models",
          link: "https://ai.google.dev/models/gemini",
        },
        {
          prop: "agency",
          placeholder: "仅支持 http 代理",
          tip: "例如：http://proxy.com",
        },
      ],
    },
    grok: {
      extraFields: [
        {
          prop: "key",
          placeholder: "Grok API Key",
          link: "https://docs.x.ai/docs/tutorial",
        },
        {
          prop: "models",
          link: "https://docs.x.ai/docs/models",
        },
      ],
    },
    ollama: {
      extraFields: [
        {
          prop: "base_url",
          placeholder: "http://localhost:11434",
          tip: "例如：http://localhost:11434",
        },
        {
          prop: "models",
          tip: "点击下方按钮可获取默认模型列表",
        },
      ],
    },
    zhipu: {
      extraFields: [
        {
          prop: "key",
          placeholder: "智谱 API Key",
          link: "https://open.bigmodel.cn/usercenter/apikeys",
        },
        {
          prop: "models",
          link: "https://open.bigmodel.cn/dev/api",
        },
      ],
    },
    qianwen: {
      extraFields: [
        {
          prop: "key",
          placeholder: "通义千问 API Key",
          link: "https://bailian.console.aliyun.com/",
        },
        {
          prop: "models",
          link: "https://help.aliyun.com/zh/dashscope/developer-reference/the-models",
        },
      ],
    },
    wenxin: {
      extraFields: [
        {
          prop: "key",
          placeholder: "文心一言 API Key",
          link: "https://console.bce.baidu.com/ai/#/ai/wenxinworkshop/overview/index",
        },
        {
          prop: "models",
          link: "https://cloud.baidu.com/doc/WENXINWORKSHOP/s/Nlks5zkzu",
        },
      ],
    },
  },
}
