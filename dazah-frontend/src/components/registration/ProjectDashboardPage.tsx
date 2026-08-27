import Link from 'next/link'
import { Card, Col, Row, Space, Statistic, Typography } from 'antd'

import type { ProjectOverview } from '@/types/registration'

interface ProjectDashboardPageProps {
  overview: ProjectOverview
}

export default function ProjectDashboardPage({ overview }: ProjectDashboardPageProps) {
  return (
    <Space orientation="vertical" size={16} style={{ width: '100%' }}>
      <Typography.Title level={3} style={{ marginBottom: 0 }}>
        {overview.module_name}
      </Typography.Title>

      <Row gutter={[16, 16]}>
        {overview.modules.map((module) => (
          <Col xs={24} lg={12} key={module.key}>
            <Card
              title={<Typography.Text strong>{module.name}</Typography.Text>}
              extra={<Link href={module.path}>进入页面</Link>}
              styles={{ body: { paddingTop: 12 } }}
            >
              <Space orientation="vertical" size={16} style={{ width: '100%' }}>
                <Row gutter={12}>
                  <Col span={12}>
                    <Card size="small">
                      <Statistic title="记录数" value={module.total_records} />
                    </Card>
                  </Col>
                  <Col span={12}>
                    <Card size="small">
                      <Statistic title="子页数" value={module.sheet_count} />
                    </Card>
                  </Col>
                </Row>

                <div>
                  <Typography.Text strong>子页面入口</Typography.Text>
                  {module.child_pages.length > 0 ? (
                    <div style={{ marginTop: 8 }}>
                      {module.child_pages.map((item) => (
                        <div key={item.key} style={{ padding: '4px 0' }}>
                          <Link href={item.path}>{item.name}</Link>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div style={{ marginTop: 8 }}>
                      <Typography.Text type="secondary">当前还没有配置子页面</Typography.Text>
                    </div>
                  )}
                </div>
              </Space>
            </Card>
          </Col>
        ))}
      </Row>
    </Space>
  )
}
