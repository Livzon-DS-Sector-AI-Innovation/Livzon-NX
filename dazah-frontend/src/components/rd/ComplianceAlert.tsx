'use client'

import { Alert, Space } from 'antd'
import { WarningOutlined, InfoCircleOutlined } from '@ant-design/icons'

interface ComplianceAlertProps {
  q3cClass1Count: number
  q3cUnknownCount: number
  q3dClass1Found: string[]
  q3dClass2BIntentionalCount: number
}

export function ComplianceAlert({ 
  q3cClass1Count, 
  q3cUnknownCount, 
  q3dClass1Found,
  q3dClass2BIntentionalCount 
}: ComplianceAlertProps) {
  const alerts = []

  if (q3cClass1Count > 0) {
    alerts.push(
      <Alert
        key="q3c-class1"
        title={`检出 ${q3cClass1Count} 种 Class 1 溶剂`}
        description={
          <span>
            <strong>根据 ICH Q3C 第 3.1 节：</strong>Class 1 溶剂不应使用，除非能提供<strong>强有力的科学依据</strong>，即使残留量低于限值。
          </span>
        }
        type="error"
        showIcon
        icon={<WarningOutlined />}
        style={{ borderColor: '#e03131' }}
      />
    )
  }

  if (q3cUnknownCount > 0) {
    alerts.push(
      <Alert
        key="q3c-unknown"
        title={`检出 ${q3cUnknownCount} 种未列入 ICH Q3C 的溶剂`}
        description="这些溶剂可能需要根据 ICH Q3C 第 5 节进行毒理学评估。"
        type="warning"
        showIcon
        icon={<InfoCircleOutlined />}
        style={{ borderColor: '#dd5b00' }}
      />
    )
  }

  if (q3dClass1Found.length > 0) {
    alerts.push(
      <Alert
        key="q3d-class1"
        title={`文中检出 ${q3dClass1Found.length} 种 Class 1 元素：${q3dClass1Found.join('、')}`}
        description={
          <span>
            <strong>根据 ICH Q3D(R2)：</strong>1 类元素（Cd、Pb、As、Hg）为人体毒物，必须在风险评估中评估所有潜在来源和给药途径。
          </span>
        }
        type="error"
        showIcon
        icon={<WarningOutlined />}
        style={{ borderColor: '#e03131' }}
      />
    )
  }

  if (q3dClass2BIntentionalCount > 0) {
    alerts.push(
      <Alert
        key="q3d-class2b"
        title={`检出 ${q3dClass2BIntentionalCount} 种有意添加的 Class 2B 元素`}
        description="2B 类元素有意添加，需要进行风险评估。"
        type="info"
        showIcon
        icon={<InfoCircleOutlined />}
        style={{ borderColor: '#0075de' }}
      />
    )
  }

  if (alerts.length === 0) {
    return (
      <Alert
        title="未发现高风险杂质"
        description="未在工艺文件中检出差出限值或高风险类别的元素/溶剂。"
        type="success"
        showIcon
        style={{ marginBottom: 16 }}
      />
    )
  }

  return <Space orientation="vertical" style={{ width: '100%', marginBottom: 16 }}>{alerts}</Space>
}
