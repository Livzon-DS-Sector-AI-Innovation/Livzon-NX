import { Typography } from 'antd'
import type { ReactNode } from 'react'

interface FeishuConfigPageHeaderProps {
  moduleLabel: string
  actions?: ReactNode
}

export function FeishuConfigPageHeader({ moduleLabel, actions }: FeishuConfigPageHeaderProps) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div>
        <Typography.Title level={3} className="!mb-1">飞书数据源</Typography.Title>
        <Typography.Text type="secondary">
          {moduleLabel}统一维护一组应用凭据、多个 Wiki/Base、页面映射和只读本地镜像。
        </Typography.Text>
      </div>
      {actions}
    </div>
  )
}
