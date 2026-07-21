'use client'

import { Card, Table, Tag, Typography, Row, Col, Alert, Space } from 'antd'
import { SafetyCertificateOutlined, ToolOutlined } from '@ant-design/icons'

const { Text } = Typography

interface Solvent {
  name_en: string
  name_cn: string
  class: string
  limit_ppm?: number
  pde_mg_day?: number
  steps_used?: (string | number)[]
}

interface ControlStrategyProps {
  solvents: Solvent[]
}

function classLabel(cls: string): { text: string; color: string } {
  const map: Record<string, { text: string; color: string }> = {
    class1: { text: 'Class 1', color: 'red' },
    class2: { text: 'Class 2', color: 'orange' },
    class3: { text: 'Class 3', color: 'green' },
    unknown: { text: '未列出', color: 'default' },
  }
  return map[cls] || { text: cls, color: 'default' }
}

export function ControlStrategy({ solvents }: ControlStrategyProps) {
  // Class 2 solvents require batch testing
  const batchTesting = solvents.filter(s => s.class === 'class2')
  // Class 3 solvents can use LOD or GC, may qualify for 10% process control
  const processControl = solvents.filter(s => s.class === 'class3')

  if (batchTesting.length === 0 && processControl.length === 0) {
    return null
  }

  const columns = [
    {
      title: '溶剂',
      key: 'name',
      width: 180,
      render: (_: any, record: Solvent) => (
        <div>
          <div>{record.name_cn}</div>
          {record.name_cn !== record.name_en && (
            <div style={{ fontSize: 12, color: '#999' }}>{record.name_en}</div>
          )}
        </div>
      ),
    },
    {
      title: 'ICH 类别',
      dataIndex: 'class',
      key: 'class',
      width: 90,
      render: (cls: string) => {
        const { text, color } = classLabel(cls)
        return <Tag color={color}>{text}</Tag>
      },
    },
    {
      title: '限值 (ppm)',
      dataIndex: 'limit_ppm',
      key: 'limit_ppm',
      width: 100,
      render: (val: any) => {
        if (val == null) return '-'
        return typeof val === 'number' ? val.toFixed(0) : val
      },
    },
    {
      title: '使用步骤',
      key: 'steps',
      width: 120,
      render: (_: any, record: Solvent) => {
        if (!record.steps_used || record.steps_used.length === 0) return '-'
        return record.steps_used.join(', ')
      },
    },
  ]

  return (
    <Card title="需要控制的溶剂" size="small" style={{ marginBottom: 16 }}>
      <Row gutter={16}>
        {batchTesting.length > 0 && (
          <Col span={batchTesting.length > 0 && processControl.length > 0 ? 12 : 24}>
            <div style={{ marginBottom: 12 }}>
              <Space style={{ marginBottom: 8 }}>
                <SafetyCertificateOutlined style={{ color: '#dd5b00' }} />
                <Text strong style={{ fontSize: 14 }}>2.1 批批检验</Text>
                <Tag color="orange">{batchTesting.length} 种</Tag>
              </Space>
            </div>
            <Table
              columns={columns}
              dataSource={batchTesting}
              rowKey="name_en"
              pagination={false}
              size="small"
              scroll={{ x: 500 }}
            />
            <div style={{ marginTop: 8, fontSize: 12, color: '#666' }}>
              根据 ICH Q3C 第 3.5 节，Class 2 溶剂必须使用 GC 进行定量测试。
            </div>
          </Col>
        )}
        {processControl.length > 0 && (
          <Col span={batchTesting.length > 0 && processControl.length > 0 ? 12 : 24}>
            <div style={{ marginBottom: 12 }}>
              <Space style={{ marginBottom: 8 }}>
                <ToolOutlined style={{ color: '#1aae39' }} />
                <Text strong style={{ fontSize: 14 }}>2.2 10% 标准 — 工艺控制</Text>
                <Tag color="green">{processControl.length} 种</Tag>
              </Space>
            </div>
            <Table
              columns={columns}
              dataSource={processControl}
              rowKey="name_en"
              pagination={false}
              size="small"
              scroll={{ x: 500 }}
            />
            <Alert
              title="10% 标准"
              description="残留量持续 ≤10% ICH 限值时，可豁免批批检验。根据 EMA/EDQM CEP 要求，需来自 6 批连续中试规模批次或 3 批连续工业生产规模批次。"
              type="info"
              showIcon
              style={{ marginTop: 8, fontSize: 12 }}
            />
          </Col>
        )}
      </Row>
    </Card>
  )
}
