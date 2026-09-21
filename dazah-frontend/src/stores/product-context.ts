"use client"

import { create } from "zustand"

// 看板/排产等页面共享的「当前产品」上下文：
// 切换后各页面（生产概览、排产计划等）按此产品取数与标记，互不串数据。
// 选择持久化到浏览器本地：刷新/重开页面保持上次的产品 Tab。

const PRODUCT_CONTEXT_STORAGE_KEY = "dazah.production.product-context"
// LV 洛伐他汀 / MV 美伐他汀：复用 MP 排产解析与看板管线的他汀产品；
// TY L-色氨酸 / FL 氟苯尼考（2%氟苯尼考预混剂）：新增产线 Tab
const KNOWN_PRODUCT_CODES = new Set([
  "FA",
  "MC",
  "DR",
  "LV",
  "MV",
  "SUMMARY",
  "TY",
  "FL",
])

interface ProductContextState {
  productCode: string
  setProductCode: (code: string) => void
}

export const useProductContextStore = create<ProductContextState>((set) => ({
  productCode: "FA",
  setProductCode: (code) => {
    set({ productCode: code })
    try {
      window.localStorage.setItem(PRODUCT_CONTEXT_STORAGE_KEY, code)
    } catch {
      // 存储不可用时仅当次会话生效
    }
  },
}))

/** 挂载后从本地存储恢复上次选择的产品 Tab（SSR 首帧保持默认 FA，避免水合错位）。 */
export function restoreProductContext(): void {
  if (typeof window === "undefined") return
  try {
    const saved = window.localStorage.getItem(PRODUCT_CONTEXT_STORAGE_KEY)
    if (saved && KNOWN_PRODUCT_CODES.has(saved)) {
      useProductContextStore.setState({ productCode: saved })
    }
  } catch {
    // 存储不可用时保持默认
  }
}
