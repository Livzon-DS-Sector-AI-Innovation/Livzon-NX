'use client'

import { ConfigProvider, App } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { getAntdTheme } from '@/lib/antd-theme'
import { useAppearance } from '@/lib/useAppearance'
import type { ColorMode } from '@/lib/appearance'
import dayjs from 'dayjs'
import 'dayjs/locale/zh-cn'

dayjs.locale('zh-cn')

interface AntdProviderProps {
  children: React.ReactNode
  fixedAppearance?: ColorMode
}

export function AntdProvider({ children, fixedAppearance }: AntdProviderProps) {
  const { resolved } = useAppearance()
  return (
    <ConfigProvider theme={getAntdTheme(fixedAppearance ?? resolved)} locale={zhCN}>
      <App>
        {children}
      </App>
    </ConfigProvider>
  )
}
