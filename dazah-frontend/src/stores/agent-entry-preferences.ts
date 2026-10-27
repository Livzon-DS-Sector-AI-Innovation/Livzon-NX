"use client"

import { useEffect } from "react"
import { create } from "zustand"

const STORAGE_KEY = "dazah.agent.floating-entry-visible"

interface AgentEntryPreferences {
  visible: boolean
  hydrated: boolean
  restore: () => void
  setVisible: (visible: boolean) => void
}

export const useAgentEntryPreferencesStore = create<AgentEntryPreferences>((set, get) => ({
  visible: true,
  hydrated: false,
  restore: () => {
    if (get().hydrated || typeof window === "undefined") return
    let visible = true
    try {
      visible = window.localStorage.getItem(STORAGE_KEY) !== "false"
    } catch {
      // 浏览器存储不可用时，使用默认显示状态。
    }
    set({ visible, hydrated: true })
  },
  setVisible: (visible) => {
    set({ visible, hydrated: true })
    try {
      window.localStorage.setItem(STORAGE_KEY, String(visible))
    } catch {
      // 存储不可用时，本次页面会话内仍然生效。
    }
  },
}))

export function useAgentEntryPreferences() {
  const preferences = useAgentEntryPreferencesStore()
  const restore = preferences.restore
  useEffect(() => restore(), [restore])
  return preferences
}
