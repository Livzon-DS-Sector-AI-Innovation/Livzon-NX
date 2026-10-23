"use client"

import { create } from "zustand"

// 设备模块五个功能页共享的「当前车间」上下文（复刻生产模块 product-context）：
// 数据以 URL query ?workshop= 为准（服务端取数、可分享），本 store 只负责
// 跨页记住上次选择——进入无参数的 /equipment/<功能> 页时由导航块自动补上。
// 选择持久化到浏览器本地：刷新/重开页面保持上次的车间。

const EQUIPMENT_WORKSHOP_STORAGE_KEY = "dazah.equipment.workshop-context"

const KNOWN_WORKSHOP_CODES = new Set([
  "101-1",
  "101-2",
  "102-1",
  "102-2",
  "103",
  "201-1",
  "201-2",
  "201-3",
  "203",
])

interface EquipmentWorkshopState {
  workshopCode: string
  setWorkshopCode: (code: string) => void
}

export const useEquipmentWorkshopStore = create<EquipmentWorkshopState>((set) => ({
  workshopCode: "201-1",
  setWorkshopCode: (code) => {
    set({ workshopCode: code })
    try {
      window.localStorage.setItem(EQUIPMENT_WORKSHOP_STORAGE_KEY, code)
    } catch {
      // 存储不可用时仅当次会话生效
    }
  },
}))

/** 挂载后从本地存储恢复上次选择的车间（SSR 首帧保持默认 201-1，避免水合错位）。 */
export function restoreEquipmentWorkshopContext(): void {
  if (typeof window === "undefined") return
  try {
    const saved = window.localStorage.getItem(EQUIPMENT_WORKSHOP_STORAGE_KEY)
    if (saved && KNOWN_WORKSHOP_CODES.has(saved)) {
      useEquipmentWorkshopStore.setState({ workshopCode: saved })
    }
  } catch {
    // 存储不可用时保持默认
  }
}
