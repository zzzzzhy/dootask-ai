export type Language = "zh" | "en"

export interface LocalizedText {
  zh: string
  en: string
}

interface TranslationTree {
  [key: string]: string | TranslationTree
}

const TRANSLATIONS: Record<Language, TranslationTree> = {
  zh: {
    app: {
      title: "AI 机器人",
      description: "浏览可用的 AI 机器人，快速开始对话，并为管理员提供统一的配置入口。",
      empty: "暂无机器人配置，请稍后再试。",
    },
    errors: {
      botNotFound: "未找到机器人信息",
      botUnavailable: "机器人暂未开启",
      loadFailed: "加载失败",
      adminOnly: "仅管理员可配置机器人。",
      botUnsupported: "该机器人暂不支持配置。",
      submitFailed: "提交失败",
      baseUrlRequired: "请先填写 Base URL",
      fetchFailed: "获取失败",
      modelsNotFound: "未找到默认模型",
    },
    success: {
      save: "修改成功",
      fetchSuccess: "获取成功",
    },
    sheet: {
      title: "AI 设置",
      loading: "配置加载中...",
      empty: "暂无可配置项。",
      reload: "重新加载",
      reset: "重置",
      submit: "提交",
      submitting: "提交中...",
      fetching: "获取中...",
      tipPrefix: "获取方式",
    },
    botCard: {
      connecting: "连接中...",
      startChat: "开始聊天",
      settings: "设置",
    },
  },
  en: {
    app: {
      title: "AI Bots",
      description: "Browse the available AI bots, start chatting quickly, and manage settings in one place.",
      empty: "No bot configuration yet. Please try again later.",
    },
    errors: {
      botNotFound: "Bot information not found",
      botUnavailable: "The bot is not available yet",
      loadFailed: "Failed to load",
      adminOnly: "Only administrators can configure bots.",
      botUnsupported: "This bot does not support configuration yet.",
      submitFailed: "Submission failed",
      baseUrlRequired: "Please fill in the Base URL first",
      fetchFailed: "Failed to fetch",
      modelsNotFound: "No default models found",
    },
    success: {
      save: "Saved successfully",
      fetchSuccess: "Fetched successfully",
    },
    sheet: {
      title: "AI Settings",
      loading: "Loading configuration...",
      empty: "No configurable items.",
      reload: "Reload",
      reset: "Reset",
      submit: "Submit",
      submitting: "Submitting...",
      fetching: "Fetching...",
      tipPrefix: "How to get",
    },
    botCard: {
      connecting: "Connecting...",
      startChat: "Start Chat",
      settings: "Settings",
    },
  },
}

export const FALLBACK_LANGUAGE: Language = "en"
const ZH_LANGUAGE_CODES = new Set(["zh", "zh-cht"])

const translateFromTree = (tree: TranslationTree, keyPath: string[]): string | undefined => {
  let current: string | TranslationTree | undefined = tree
  for (const segment of keyPath) {
    if (!current || typeof current === "string") {
      return undefined
    }
    current = current[segment]
  }
  return typeof current === "string" ? current : undefined
}

export const translateInternal = (lang: Language, key: string): string => {
  const segments = key.split(".")
  const primary = translateFromTree(TRANSLATIONS[lang], segments)
  if (primary) {
    return primary
  }
  if (lang !== FALLBACK_LANGUAGE) {
    const fallback = translateFromTree(TRANSLATIONS[FALLBACK_LANGUAGE], segments)
    if (fallback) {
      return fallback
    }
  }
  return key
}

export const detectLanguage = (): Language => {
  try {
    const params = new URLSearchParams(window.location.search)
    const raw = params.get("lang")
    if (raw) {
      const normalized = raw.trim().toLowerCase()
      if (ZH_LANGUAGE_CODES.has(normalized)) {
        return "zh"
      }
    }
  } catch {
    // ignore errors during detection and fall back to default
  }
  return FALLBACK_LANGUAGE
}

export const getLocalizedText = (localized: LocalizedText, lang: Language) =>
  localized[lang] ?? localized[FALLBACK_LANGUAGE]
