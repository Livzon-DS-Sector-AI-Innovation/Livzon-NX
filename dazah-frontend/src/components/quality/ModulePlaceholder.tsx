'use client'

import { qualityTokens } from './themeTokens'
import { Result, Card } from 'antd'
import { ExperimentOutlined } from '@ant-design/icons'

interface ModulePlaceholderProps {
  title: string
  description?: string
}

export function ModulePlaceholder({ title, description }: ModulePlaceholderProps) {
  return (
    <Card style={{ maxWidth: 600, margin: '80px auto', textAlign: 'center' }}>
      <Result
        icon={<ExperimentOutlined style={{ color: qualityTokens.primary }} />}
        title={title}
        subTitle={description || '该功能正在开发中，敬请期待'}
      />
    </Card>
  )
}
