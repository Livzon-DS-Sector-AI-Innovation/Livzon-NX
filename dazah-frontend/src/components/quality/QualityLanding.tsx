'use client'

import Link from 'next/link'
import { Card, Row, Col } from 'antd'
import {
  FileTextOutlined,
  SafetyCertificateOutlined,
  TeamOutlined,
  AuditOutlined,
  SafetyOutlined,
  SettingOutlined,
} from '@ant-design/icons'
import { QualitySyncConflictPanel } from './QualitySyncConflictPanel'

export function QualityLanding() {
  return (
    <div>
      <h1 style={{ fontSize: 22, fontWeight: 600, marginBottom: 24 }}>质量管理</h1>
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} md={8}>
          <Link href="/quality/feishu-settings">
            <Card hoverable>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <SettingOutlined style={{ fontSize: 32, color: '#0958d9' }} />
                <div>
                  <div style={{ fontSize: 16, fontWeight: 600 }}>飞书设置</div>
                  <div style={{ fontSize: 13, color: '#787671' }}>配置应用信息与 Base 表绑定</div>
                </div>
              </div>
            </Card>
          </Link>
        </Col>
        <Col xs={24} sm={12} md={8}>
          <Link href="/quality/deviations">
            <Card hoverable>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <FileTextOutlined style={{ fontSize: 32, color: '#1677ff' }} />
                <div>
                  <div style={{ fontSize: 16, fontWeight: 600 }}>偏差管理</div>
                  <div style={{ fontSize: 13, color: '#787671' }}>记录和跟踪生产偏差</div>
                </div>
              </div>
            </Card>
          </Link>
        </Col>
        <Col xs={24} sm={12} md={8}>
          <Link href="/quality/capas">
            <Card hoverable>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <SafetyCertificateOutlined style={{ fontSize: 32, color: '#1aae39' }} />
                <div>
                  <div style={{ fontSize: 16, fontWeight: 600 }}>CAPA管理</div>
                  <div style={{ fontSize: 13, color: '#787671' }}>纠正和预防措施</div>
                </div>
              </div>
            </Card>
          </Link>
        </Col>
        <Col xs={24} sm={12} md={8}>
          <Link href="/quality/department-contacts">
            <Card hoverable>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <TeamOutlined style={{ fontSize: 32, color: '#7b3ff2' }} />
                <div>
                  <div style={{ fontSize: 16, fontWeight: 600 }}>部门联系人</div>
                  <div style={{ fontSize: 13, color: '#787671' }}>配置部门联系信息</div>
                </div>
              </div>
            </Card>
          </Link>
        </Col>
        <Col xs={24} sm={12} md={8}>
          <Link href="/quality/change">
            <Card hoverable>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <AuditOutlined style={{ fontSize: 32, color: '#d46b08' }} />
                <div>
                  <div style={{ fontSize: 16, fontWeight: 600 }}>变更控制</div>
                  <div style={{ fontSize: 13, color: '#787671' }}>查看变更台账与变更计划概览</div>
                </div>
              </div>
            </Card>
          </Link>
        </Col>
        <Col xs={24} sm={12} md={8}>
          <Link href="/quality/validation">
            <Card hoverable>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <SafetyOutlined style={{ fontSize: 32, color: '#531dab' }} />
                <div>
                  <div style={{ fontSize: 16, fontWeight: 600 }}>验证与确认</div>
                  <div style={{ fontSize: 13, color: '#787671' }}>查看验证主计划和各执行子表概览</div>
                </div>
              </div>
            </Card>
          </Link>
        </Col>
      </Row>
      <div style={{ marginTop: 16 }}>
        <QualitySyncConflictPanel />
      </div>
    </div>
  )
}
