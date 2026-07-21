'use client'

import { Card, Table, Tag, Typography } from 'antd'
import { ExperimentOutlined } from '@ant-design/icons'

const { Text } = Typography

interface Solvent {
  name_en: string
  name_cn: string
  class: string
  limit_ppm?: number
}

interface TestingRecommendationsProps {
  solvents: Solvent[]
}

function classLabel(cls: string): { text: string; color: string } {
  const map: Record<string, { text: string; color: string }> = {
    class2: { text: 'Class 2', color: 'orange' },
    class3: { text: 'Class 3', color: 'green' },
  }
  return map[cls] || { text: cls, color: 'default' }
}

function getRecommendedMethod(cls: string): string {
  if (cls === 'class2') {
    return 'GC (定量分析)'
  }
  if (cls === 'class3') {
    return 'LOD ≤0.5% 或 GC'
  }
  return '-'
}

export function TestingRecommendations({ solvents }: TestingRecommendationsProps) {
  // Only Class 2 and Class 3 need testing recommendations
  const testable = solvents.filter(s => s.class === 'class2' || s.class === 'class3')

  if (testable.length === 0) {
    return null
  }

  const columns = [
    {
      title: '溶剂',
      key: 'name',
      width: 200,
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
      width: 100,
      render: (cls: string) => {
        const { text, color } = classLabel(cls)
        return <Tag color={color}>{text}</Tag>
      },
    },
    {
      title: '推荐方法',
      key: 'method',
      width: 180,
      render: (_: any, record: Solvent) => (
        <Text strong>{getRecommendedMethod(record.class)}</Text>
      ),
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
  ]

  return (
    <Card 
      title={
        <span>
          <ExperimentOutlined style={{ marginRight: 8 }} />
          推荐测试方法
        </span>
      }
      size="small"
      style={{ marginBottom: 16 }}
    >
      <Table
        columns={columns}
        dataSource={testable}
        rowKey="name_en"
        pagination={false}
        size="small"
        scroll={{ x: 600 }}
      />
      <div style={{ marginTop: 12, fontSize: 12, color: '#666', lineHeight: 1.6 }}>
        <div><strong>说明：</strong></div>
        <div>• <strong>Class 2 溶剂：</strong>根据 ICH Q3C 第 3.5 节，必须使用 GC 进行定量测试</div>
        <div>• <strong>Class 3 溶剂：</strong>根据 ICH Q3C 第 3.5 节，LOD ≤0.5% 可接受，或使用已验证的 GC 方法</div>
      </div>
    </Card>
  )
}
