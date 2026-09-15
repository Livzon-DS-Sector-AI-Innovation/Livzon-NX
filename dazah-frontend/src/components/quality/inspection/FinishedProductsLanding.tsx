'use client'

import Link from 'next/link'
import { Card, Col, Row, Space, Tag, Typography } from 'antd'
import {
  ExperimentOutlined,
  MedicineBoxOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'

const { Paragraph, Text, Title } = Typography

type ProductEntry = {
  label: string
  href: string
  description: string
  icon: React.ReactNode
}

const PRODUCTS: ProductEntry[] = [
  { label: '霉酚酸', href: '/quality/inspection/finished/mpa', description: '内控 / 高规检验台账与趋势', icon: <MedicineBoxOutlined /> },
  { label: '美伐他汀', href: '/quality/inspection/finished/mvt', description: 'DMF 等子表检验台账与趋势', icon: <ExperimentOutlined /> },
  { label: '洛伐他汀', href: '/quality/inspection/finished/lft', description: 'EP / USP 检验台账与趋势', icon: <ExperimentOutlined /> },
  { label: '多拉菌素', href: '/quality/inspection/finished/dls', description: '各客户子表检验台账与趋势', icon: <ExperimentOutlined /> },
  { label: '林可霉素', href: '/quality/inspection/finished/lkms', description: '内控 / USP / K 系列台账', icon: <ExperimentOutlined /> },
  { label: 'L-苯丙氨酸', href: '/quality/inspection/finished/bbas', description: '各客户子表检验台账与趋势', icon: <ExperimentOutlined /> },
  { label: '预混剂', href: '/quality/inspection/finished/formulations', description: '制剂检验台账与趋势', icon: <ThunderboltOutlined /> },
  { label: '色氨酸', href: '/quality/inspection/finished/tryptophan', description: '颗粒检验台账与趋势', icon: <ExperimentOutlined /> },
  { label: '纯化水', href: '/quality/inspection/finished/water', description: '纯化水检验台账与趋势', icon: <ExperimentOutlined /> },
  { label: 'PF', href: '/quality/inspection/finished/pf', description: 'PF 检验台账', icon: <ExperimentOutlined /> },
]

/** 成品检验首页：按产品进入各成品的检验台账（趋势图在台账页内）。 */
export function FinishedProductsLanding() {
  return (
    <div className="mx-auto max-w-[1440px]">
      <Space direction="vertical" size={8} className="mb-6">
        <Title level={3} className="!mb-0">
          成品检验
        </Title>
        <Paragraph type="secondary" className="!mb-0">
          按产品进入成品检验台账与趋势分析。
        </Paragraph>
      </Space>
      <Row gutter={[16, 16]}>
        {PRODUCTS.map((product) => (
          <Col xs={24} sm={12} lg={8} xl={6} key={product.href}>
            <Link href={product.href} className="block h-full">
              <Card
                hoverable
                size="small"
                title={
                  <Space>
                    <span className="text-[var(--color-primary)]">{product.icon}</span>
                    <span>{product.label}</span>
                    <Tag color="success">台账</Tag>
                  </Space>
                }
              >
                <Text type="secondary">{product.description}</Text>
              </Card>
            </Link>
          </Col>
        ))}
      </Row>
    </div>
  )
}