'use client'

import { Card, Typography, Tag } from 'antd'
import { PauseCircleOutlined } from '@ant-design/icons'

const { Title, Text } = Typography

export default function Page() {
  return (
    <div className="p-6">
      <Title level={4}><PauseCircleOutlined className="mr-2" />202车间</Title>
      <Tag color="default">停产中</Tag>
      <Card className="mt-6" style={{ minHeight: 300, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Text type="secondary">该车间当前处于停产状态，暂无生产数据</Text>
      </Card>
    </div>
  )
}
