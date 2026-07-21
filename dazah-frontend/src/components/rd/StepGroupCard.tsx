'use client'

import { Card, Table, Tag, Collapse, Space } from 'antd'
import { ExperimentOutlined } from '@ant-design/icons'

interface StepSolvent {
  solvent: string
  original_name?: string
  class: string
  limit?: number | string
  pde?: number | null
  purpose?: string
  amount?: string
  matched_as?: string
}

interface StepData {
  step_number: string | number
  step_title: string
  solvents: StepSolvent[]
  solvent_count: number
}

interface StepGroupCardProps {
  steps: StepData[]
}

function getStepBorderColor(solvents: StepSolvent[]): string {
  const hasClass1 = solvents.some(s => s.class === 'class1')
  const hasClass2 = solvents.some(s => s.class === 'class2')
  if (hasClass1) return '#e03131'
  if (hasClass2) return '#dd5b00'
  return '#d9d9d9'
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

function purposeLabel(purpose: string): string {
  const map: Record<string, string> = {
    reaction: '反应',
    purification: '纯化',
    extraction: '萃取',
    crystallization: '结晶',
    washing: '洗涤',
  }
  return map[purpose] || purpose || '-'
}

export function StepGroupCard({ steps }: StepGroupCardProps) {
  if (!steps || steps.length === 0) return null

  const columns = [
    {
      title: '溶剂名称',
      key: 'name',
      width: 200,
      render: (_: any, record: StepSolvent) => (
        <div>
          <div>{record.original_name || record.solvent}</div>
          {record.original_name && record.solvent !== record.original_name && (
            <div style={{ fontSize: 12, color: '#999' }}>{record.solvent}</div>
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
      title: '用途',
      dataIndex: 'purpose',
      key: 'purpose',
      width: 100,
      render: (val: string) => purposeLabel(val),
    },
    {
      title: '用量',
      dataIndex: 'amount',
      key: 'amount',
      width: 120,
      render: (val: string) => val || '-',
    },
    {
      title: 'ICH 限值 (ppm)',
      key: 'limit',
      width: 120,
      render: (_: any, record: StepSolvent) => {
        if (record.limit == null) return '-'
        if (typeof record.limit === 'number') return record.limit.toFixed(0)
        return record.limit
      },
    },
    {
      title: 'PDE (mg/天)',
      dataIndex: 'pde',
      key: 'pde',
      width: 110,
      render: (val: any) => {
        if (val == null) return '-'
        if (typeof val === 'number') return val.toFixed(1)
        return val
      },
    },
  ]

  const items = steps.map((step, index) => {
    const borderColor = getStepBorderColor(step.solvents)
    const hasClass1 = step.solvents.some(s => s.class === 'class1')
    const stepLabel = (
      <Space>
        <ExperimentOutlined style={{ color: borderColor === '#d9d9d9' ? '#999' : borderColor }} />
        <span style={{ fontWeight: 500 }}>
          {step.step_number || `步骤 ${index + 1}`}{step.step_title ? `: ${step.step_title}` : ''}
        </span>
        <Tag style={{ marginLeft: 4 }}>{step.solvent_count} 种溶剂</Tag>
        {hasClass1 && <Tag color="red">Class 1</Tag>}
      </Space>
    )

    return {
      key: String(index),
      label: stepLabel,
      children: (
        <Table
          columns={columns}
          dataSource={step.solvents}
          rowKey={(r) => `${r.solvent}-${r.original_name}-${r.purpose}-${r.amount}`}
          pagination={false}
          size="small"
          scroll={{ x: 700 }}
        />
      ),
      style: {
        borderLeft: `3px solid ${borderColor}`,
        marginBottom: 8,
      },
    }
  })

  return (
    <Card
      title="各步骤使用的溶剂"
      size="small"
      style={{ marginBottom: 16 }}
    >
      <Collapse
        items={items}
        defaultActiveKey={['0']}
        ghost
      />
    </Card>
  )
}
