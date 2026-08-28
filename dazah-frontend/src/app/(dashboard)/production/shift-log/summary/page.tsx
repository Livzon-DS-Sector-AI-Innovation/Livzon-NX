'use client'

import { Card, Typography, Divider, Tag } from 'antd'
import { FileTextOutlined } from '@ant-design/icons'

const { Title, Text, Paragraph } = Typography

export default function SummaryPage() {
  return (
    <div className="p-6">
      <Title level={4}><FileTextOutlined className="mr-2" />班次运行摘要</Title>
      <Tag color="default">待开发功能</Tag>

      <Divider />

      <Card style={{ maxWidth: 800 }}>
        <Paragraph strong style={{ fontSize: 15 }}>定位</Paragraph>
        <Paragraph type="secondary">
          本班次的&ldquo;生产战报&rdquo;，在交班前由系统一键自动配平生成。
        </Paragraph>

        <Paragraph strong style={{ fontSize: 15, marginTop: 24 }}>包含内容</Paragraph>
        <Paragraph>
          <Text strong>物料阶段统计：</Text>
          <Text type="secondary">本班次内车间累计消耗的大宗原辅料（葡萄糖、液氨、消泡剂）总量统计。</Text>
        </Paragraph>
        <Paragraph>
          <Text strong>能耗阶段统计：</Text>
          <Text type="secondary">本班次运行期间，车间总水、电、蒸汽的宏观计量数据（与公用系统对接）。</Text>
        </Paragraph>

        <Paragraph strong style={{ fontSize: 15, marginTop: 24 }}>AI 价值</Paragraph>
        <Paragraph type="secondary">
          自动将死板的数字转化为可视化看板，帮车间主任和总监看清每一班的能耗效率与成本账。
        </Paragraph>
      </Card>
    </div>
  )
}
