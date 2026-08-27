'use client'

import Link from 'next/link'
import type { ReactNode } from 'react'
import { Card, Col, Empty, Row, Space, Tag, Typography } from 'antd'
import {
  ExperimentOutlined,
  InboxOutlined,
  ToolOutlined,
} from '@ant-design/icons'

const { Paragraph, Text, Title } = Typography

type Section = {
  title: string
  description: string
  href: string
  icon: ReactNode
  links: Array<{ label: string; href: string }>
}

const sections: Section[] = [
  {
    title: '物品管理',
    description: '管理实验室物品库存、入库和出库记录。',
    href: '/quality/inspection/items/inventory',
    icon: <InboxOutlined />,
    links: [
      { label: '库存台账', href: '/quality/inspection/items/inventory' },
      { label: '入库记录', href: '/quality/inspection/items/inbound' },
      { label: '出库记录', href: '/quality/inspection/items/outbound' },
    ],
  },
  {
    title: '仪器管理',
    description: '管理仪器设备、资产、校准、维护和维修。',
    href: '/quality/inspection/instruments/equipment',
    icon: <ToolOutlined />,
    links: [
      { label: '仪器设备', href: '/quality/inspection/instruments/equipment' },
      { label: '资产台账', href: '/quality/inspection/instruments/assets' },
      { label: '校准计划', href: '/quality/inspection/instruments/calibration' },
      { label: '维护保养', href: '/quality/inspection/instruments/maintenance' },
      { label: '维修记录', href: '/quality/inspection/instruments/repair' },
      { label: '年度计划', href: '/quality/inspection/instruments/plans' },
    ],
  },
  {
    title: '成品检验',
    description: '按产品进入成品检验台账与趋势分析。',
    href: '/quality/inspection/finished/mpa',
    icon: <ExperimentOutlined />,
    links: [
      { label: '霉酚酸', href: '/quality/inspection/finished/mpa' },
      { label: '美伐他汀', href: '/quality/inspection/finished/mvt' },
      { label: '洛伐他汀', href: '/quality/inspection/finished/lft' },
      { label: '多拉菌素', href: '/quality/inspection/finished/dls' },
      { label: '林可霉素', href: '/quality/inspection/finished/lkms' },
      { label: 'L-苯丙氨酸', href: '/quality/inspection/finished/bbas' },
      { label: '预混剂', href: '/quality/inspection/finished/formulations' },
      { label: '色氨酸', href: '/quality/inspection/finished/tryptophan' },
      { label: '纯化水', href: '/quality/inspection/finished/water' },
    ],
  },
]

export function InspectionSectionLanding() {
  return (
    <div className="mx-auto max-w-[1440px]">
      <Space direction="vertical" size={8} className="mb-6">
        <Title level={3} className="!mb-0">质量检验</Title>
        <Paragraph type="secondary" className="!mb-0">
          选择已迁移的质量检验子模块进入业务台账；页面只展示真实可访问的入口。
        </Paragraph>
      </Space>
      <Row gutter={[16, 16]}>
        {sections.map((section) => (
          <Col xs={24} lg={8} key={section.title}>
            <Card
              title={
                <Space>
                  <span className="text-[var(--color-primary)]">{section.icon}</span>
                  <span>{section.title}</span>
                  <Tag color="success">可用入口</Tag>
                </Space>
              }
              extra={<Link href={section.href}>进入</Link>}
            >
              <Text type="secondary">{section.description}</Text>
              <div className="mt-4 grid grid-cols-2 gap-2">
                {section.links.map((link) => (
                  <Link
                    href={link.href}
                    key={link.href}
                    className="rounded border border-[var(--color-border)] px-3 py-2 text-sm hover:border-[var(--color-primary)]"
                  >
                    {link.label}
                  </Link>
                ))}
              </div>
            </Card>
          </Col>
        ))}
      </Row>
      {sections.length === 0 && <Empty description="暂无可访问的质量检验入口" />}
    </div>
  )
}
