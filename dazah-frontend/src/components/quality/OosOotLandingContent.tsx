'use client'

import Link from 'next/link'
import { Card, Row, Col } from 'antd'
import {
  FileTextOutlined,
  SendOutlined,
  OrderedListOutlined,
  UnorderedListOutlined,
  ApartmentOutlined,
  ProfileOutlined,
} from '@ant-design/icons'

export function OosOotLandingContent() {
  return (
    <div>
      <h1 style={{ fontSize: 22, fontWeight: 600, marginBottom: 24 }}>OOS/OOT管理</h1>
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} md={8}>
          <Link href="/quality/oos-oot/report-records">
            <Card hoverable>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <FileTextOutlined style={{ fontSize: 32, color: '#1677ff' }} />
                <div>
                  <div style={{ fontSize: 16, fontWeight: 600 }}>OOSOOT报告记录</div>
                  <div style={{ fontSize: 13, color: '#787671' }}>查看和管理OOS/OOT报告记录</div>
                </div>
              </div>
            </Card>
          </Link>
        </Col>
        <Col xs={24} sm={12} md={8}>
          <Link href="/quality/oos-oot/investigation-push">
            <Card hoverable>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <SendOutlined style={{ fontSize: 32, color: '#1aae39' }} />
                <div>
                  <div style={{ fontSize: 16, fontWeight: 600 }}>OOSOOT调查推送记录</div>
                  <div style={{ fontSize: 13, color: '#787671' }}>查看和管理调查推送记录</div>
                </div>
              </div>
            </Card>
          </Link>
        </Col>
        <Col xs={24} sm={12} md={8}>
          <Link href="/quality/oos-oot/oos-ledger">
            <Card hoverable>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <OrderedListOutlined style={{ fontSize: 32, color: '#7b3ff2' }} />
                <div>
                  <div style={{ fontSize: 16, fontWeight: 600 }}>OOS台账</div>
                  <div style={{ fontSize: 13, color: '#787671' }}>OOS超出标准结果台账</div>
                </div>
              </div>
            </Card>
          </Link>
        </Col>
        <Col xs={24} sm={12} md={8}>
          <Link href="/quality/oos-oot/oot-ledger">
            <Card hoverable>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <UnorderedListOutlined style={{ fontSize: 32, color: '#d46b08' }} />
                <div>
                  <div style={{ fontSize: 16, fontWeight: 600 }}>OOT台账</div>
                  <div style={{ fontSize: 13, color: '#787671' }}>OOT超出趋势结果台账</div>
                </div>
              </div>
            </Card>
          </Link>
        </Col>
        <Col xs={24} sm={12} md={8}>
          <Link href="/quality/oos-oot/oot-limits">
            <Card hoverable>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <ProfileOutlined style={{ fontSize: 32, color: '#c41d7f' }} />
                <div>
                  <div style={{ fontSize: 16, fontWeight: 600 }}>各产品OOT限度</div>
                  <div style={{ fontSize: 13, color: '#787671' }}>维护各产品OOT限度通知单明细</div>
                </div>
              </div>
            </Card>
          </Link>
        </Col>
        <Col xs={24} sm={12} md={8}>
          <Link href="/quality/oos-oot/product-departments">
            <Card hoverable>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <ApartmentOutlined style={{ fontSize: 32, color: '#531dab' }} />
                <div>
                  <div style={{ fontSize: 16, fontWeight: 600 }}>产品涉及部门</div>
                  <div style={{ fontSize: 13, color: '#787671' }}>管理产品涉及的部门信息</div>
                </div>
              </div>
            </Card>
          </Link>
        </Col>
      </Row>
    </div>
  )
}
