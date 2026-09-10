"use client"

import { create } from "zustand"

// 看板/排产等页面共享的「当前产品」上下文：
// 切换后各页面（生产概览、排产计划等）按此产品取数与标记，互不串数据。
interface ProductContextState {
  productCode: string
  setProductCode: (code: string) => void
}

export const useProductContextStore = create<ProductContextState>((set) => ({
  productCode: "FA",
  setProductCode: (code) => set({ productCode: code }),
}))
