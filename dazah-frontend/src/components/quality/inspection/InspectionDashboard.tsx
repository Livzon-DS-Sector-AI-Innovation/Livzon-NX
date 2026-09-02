'use client'

import { qualityTokens } from '../themeTokens'
import { Card, Row, Col } from 'antd'
import {
  BgColorsOutlined,
  ExperimentOutlined,
  ToolOutlined,
  CheckCircleOutlined,
  GoldOutlined,
} from '@ant-design/icons'
import { useRouter } from 'next/navigation'

const inspectionCards = [
  {
    key: 'items',
    title: '物品管理',
    description: '实验室物品、试剂、耗材的管理',
    icon: <ToolOutlined style={{ fontSize: 32, color: qualityTokens.primary }} />,
    path: '/quality/inspection/items/inventory',
  },
  {
    key: 'instruments',
    title: '仪器管理',
    description: '实验室仪器设备的台账、校准、维护管理',
    icon: <ExperimentOutlined style={{ fontSize: 32, color: '#52c41a' }} />,
    path: '/quality/inspection/instruments/equipment',
  },
  {
    key: 'finished',
    title: '成品检验',
    description: '成品检验数据录入、查询与统计分析',
    icon: <CheckCircleOutlined style={{ fontSize: 32, color: qualityTokens.warning }} />,
    path: '/quality/inspection/finished/mpa',
  },
  {
    key: 'solid',
    title: '固体物料检验',
    description: '固体原辅料的检验数据管理',
    icon: <GoldOutlined style={{ fontSize: 32, color: '#722ed1' }} />,
    path: '/quality/inspection/solid',
  },
  {
    key: 'liquid',
    title: '液体物料检验',
    description: '液体原辅料的检验数据管理',
    icon: <BgColorsOutlined style={{ fontSize: 32, color: '#13c2c2' }} />,
    path: '/quality/inspection/liquid',
  },
]

export function InspectionDashboard() {
  const router = useRouter()

  return (
    <div style={{ padding: 24 }}>
      <h2 style={{ marginBottom: 24, fontSize: 20, fontWeight: 600 }}>质量检验</h2>
      <Row gutter={[16, 16]}>
        {inspectionCards.map((card) => (
          <Col key={card.key} xs={24} sm={12} lg={8} xl={6}>
            <Card
              hoverable
              onClick={() => router.push(card.path)}
              style={{ textAlign: 'center', height: '100%' }}
            >
              <div style={{ marginBottom: 12 }}>{card.icon}</div>
              <Card.Meta title={card.title} description={card.description} />
            </Card>
          </Col>
        ))}
      </Row>
    </div>
  )
}
