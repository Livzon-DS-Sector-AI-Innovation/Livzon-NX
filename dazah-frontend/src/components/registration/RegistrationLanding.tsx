'use client'

import Link from 'next/link'
import { Card, Col, Row } from 'antd'
import {
  AuditOutlined,
  FileSearchOutlined,
  FileTextOutlined,
  SafetyCertificateOutlined,
  DollarOutlined,
  BookOutlined,
} from '@ant-design/icons'

export function RegistrationLanding() {
  return (
    <div>
      <h1 style={{ fontSize: 22, fontWeight: 600, marginBottom: 24 }}>注册管理</h1>
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} md={8}>
          <Link href="/registration/project">
            <Card hoverable>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <FileSearchOutlined style={{ fontSize: 32, color: '#1677ff' }} />
                <div>
                  <div style={{ fontSize: 16, fontWeight: 600 }}>申报项目</div>
                  <div style={{ fontSize: 13, color: '#787671' }}>进入申报项目父级页，查看申报台账及对应入口</div>
                </div>
              </div>
            </Card>
          </Link>
        </Col>
        <Col xs={24} sm={12} md={8}>
          <Link href="/registration/authorization-letter">
            <Card hoverable>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <FileTextOutlined style={{ fontSize: 32, color: '#1aae39' }} />
                <div>
                  <div style={{ fontSize: 16, fontWeight: 600 }}>授权书管理</div>
                  <div style={{ fontSize: 13, color: '#787671' }}>查看授权书台账、FDA 信息和资料下载</div>
                </div>
              </div>
            </Card>
          </Link>
        </Col>
        <Col xs={24} sm={12} md={8}>
          <Link href="/registration/certificate-management">
            <Card hoverable>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <SafetyCertificateOutlined style={{ fontSize: 32, color: '#722ed1' }} />
                <div>
                  <div style={{ fontSize: 16, fontWeight: 600 }}>证书管理</div>
                  <div style={{ fontSize: 13, color: '#787671' }}>查看注册证、GMP 证书及到期提醒配置</div>
                </div>
              </div>
            </Card>
          </Link>
        </Col>
        <Col xs={24} sm={12} md={8}>
          <Link href="/registration/regulation">
            <Card hoverable>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <AuditOutlined style={{ fontSize: 32, color: '#d46b08' }} />
                <div>
                  <div style={{ fontSize: 16, fontWeight: 600 }}>法规跟踪</div>
                  <div style={{ fontSize: 13, color: '#787671' }}>跟踪近期开启抓取的国内外法规更新信息</div>
                </div>
              </div>
            </Card>
          </Link>
        </Col>
        <Col xs={24} sm={12} md={8}>
          <Link href="/registration/fees">
            <Card hoverable>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <DollarOutlined style={{ fontSize: 32, color: '#cf1322' }} />
                <div>
                  <div style={{ fontSize: 16, fontWeight: 600 }}>注册费用</div>
                  <div style={{ fontSize: 13, color: '#787671' }}>管理注册费、检验费、代理费等费用台账</div>
                </div>
              </div>
            </Card>
          </Link>
        </Col>
        <Col xs={24} sm={12} md={8}>
          <Link href="/registration/knowledge">
            <Card hoverable>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <BookOutlined style={{ fontSize: 32, color: '#08979c' }} />
                <div>
                  <div style={{ fontSize: 16, fontWeight: 600 }}>注册知识库</div>
                  <div style={{ fontSize: 13, color: '#787671' }}>沉淀法规解读、申报经验和常见问题</div>
                </div>
              </div>
            </Card>
          </Link>
        </Col>
      </Row>
    </div>
  )
}
