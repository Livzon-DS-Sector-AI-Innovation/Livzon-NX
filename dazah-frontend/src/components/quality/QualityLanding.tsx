'use client'

import { qualityTokens } from './themeTokens'
import Link from 'next/link'
import { Card, Row, Col } from 'antd'
import {
  ApartmentOutlined,
  AuditOutlined,
  DatabaseOutlined,
  ExperimentOutlined,
  FileTextOutlined,
  FolderOpenOutlined,
  NotificationOutlined,
  RollbackOutlined,
  SafetyCertificateOutlined,
  SafetyOutlined,
  SettingOutlined,
  TeamOutlined,
  WarningOutlined,
} from '@ant-design/icons'

export function QualityLanding() {
  const cards = [
    {
      title: '飞书设置',
      description: '配置质量模块飞书应用和各台账同步映射',
      href: '/quality/feishu-settings',
      icon: <SettingOutlined style={{ fontSize: 32, color: '#0958d9' }} />,
    },
    {
      title: '文件管理',
      description: '按部门浏览和管理各部门文件目录',
      href: '/quality/documents',
      icon: <FolderOpenOutlined style={{ fontSize: 32, color: '#2f54eb' }} />,
    },
    {
      title: '偏差管理',
      description: '记录和跟踪生产偏差',
      href: '/quality/deviations',
      icon: <FileTextOutlined style={{ fontSize: 32, color: qualityTokens.primary }} />,
    },
    {
      title: 'CAPA管理',
      description: '纠正和预防措施',
      href: '/quality/capas',
      icon: <SafetyCertificateOutlined style={{ fontSize: 32, color: qualityTokens.success }} />,
    },
    {
      title: '投诉管理',
      description: '查看客户投诉台账和处理记录',
      href: '/quality/complaints',
      icon: <NotificationOutlined style={{ fontSize: 32, color: '#d46b08' }} />,
    },
    {
      title: '部门联系人',
      description: '配置部门联系信息',
      href: '/quality/department-contacts',
      icon: <TeamOutlined style={{ fontSize: 32, color: '#7b3ff2' }} />,
    },
    {
      title: '质量检验',
      description: '查看检验仪表盘与分组明细',
      href: '/quality/inspection',
      icon: <ExperimentOutlined style={{ fontSize: 32, color: '#08979c' }} />,
    },
    {
      title: 'OOS/OOT管理',
      description: '管理报告记录、调查推送及台账',
      href: '/quality/oos-oot',
      icon: <WarningOutlined style={{ fontSize: 32, color: '#cf1322' }} />,
    },
    {
      title: '产品质量回顾',
      description: '查看产品质量标准与回顾页',
      href: '/quality/product-quality',
      icon: <DatabaseOutlined style={{ fontSize: 32, color: '#722ed1' }} />,
    },
    {
      title: '退货召回',
      description: '处理退货申请和退货台账',
      href: '/quality/return-recalls',
      icon: <RollbackOutlined style={{ fontSize: 32, color: qualityTokens.warning }} />,
    },
    {
      title: '供应商管理',
      description: '查看供应商资质仪表盘和台账',
      href: '/quality/suppliers',
      icon: <ApartmentOutlined style={{ fontSize: 32, color: '#531dab' }} />,
    },
    {
      title: '变更控制',
      description: '查看变更台账与变更计划概览',
      href: '/quality/change',
      icon: <AuditOutlined style={{ fontSize: 32, color: '#d46b08' }} />,
    },
    {
      title: '验证与确认',
      description: '查看验证主计划和各执行子表概览',
      href: '/quality/validation',
      icon: <SafetyOutlined style={{ fontSize: 32, color: '#531dab' }} />,
    },
  ]

  return (
    <div>
      <h1 style={{ fontSize: 22, fontWeight: 600, marginBottom: 24 }}>质量管理</h1>
      <Row gutter={[16, 16]}>
        {cards.map((card) => (
          <Col xs={24} sm={12} md={8} key={card.href}>
            <Link href={card.href}>
              <Card hoverable>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  {card.icon}
                  <div>
                    <div style={{ fontSize: 16, fontWeight: 600 }}>{card.title}</div>
                    <div style={{ fontSize: 13, color: qualityTokens.textMuted }}>{card.description}</div>
                  </div>
                </div>
              </Card>
            </Link>
          </Col>
        ))}
      </Row>
    </div>
  )
}
