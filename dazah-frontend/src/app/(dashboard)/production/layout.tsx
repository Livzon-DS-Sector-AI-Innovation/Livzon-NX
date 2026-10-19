'use client'

import { ConfigProvider } from 'antd'
import type { ReactNode } from 'react'
import overlayStyles from '@/components/production/production-overlays.module.css'

export default function ProductionLayout({ children }: { children: ReactNode }) {
  return (
    <ConfigProvider datePicker={{ classNames: { popup: { root: overlayStyles.datePickerPopup } } }}>
      {children}
    </ConfigProvider>
  )
}
