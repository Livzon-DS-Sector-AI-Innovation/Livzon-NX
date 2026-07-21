'use client'

import { useState, useEffect, useCallback } from 'react'
import { 
  App,
  Card, 
  Button, 
  Upload, 
  Tabs, 
  Table, 
  Tag, 
  Descriptions,
  Space,
  Typography,
  Select,
  Popconfirm,
  Collapse
} from 'antd'
import { 
  UploadOutlined, 
  DownloadOutlined,
  HistoryOutlined,
  DeleteOutlined,
  EyeOutlined,
  ExperimentOutlined
} from '@ant-design/icons'
import { ComplianceAlert } from './ComplianceAlert'
import { StepGroupCard } from './StepGroupCard'
import { ControlStrategy } from './ControlStrategy'
import { TestingRecommendations } from './TestingRecommendations'

const { Text } = Typography
const { Option } = Select

interface ElementResult {
  symbol: string
  source: string
  intentionally_added: boolean
  assessment_required: boolean
  q3d_class: string
  oral_pde?: number
  parenteral_pde?: number
  inhalation_pde?: number
  cutaneous_pde?: number
  ctcl?: number
  oral_assess: boolean
  parenteral_assess: boolean
  inhalation_assess: boolean
  cutaneous_assess: boolean
  notes: string
  found_in_text?: boolean
  needs_assessment?: boolean
  pde_for_route?: number
  control_threshold?: number
  ctcl_applicable?: boolean
}

interface SolventResult {
  name_en: string
  name_cn: string
  class: string
  limit_ppm?: number
  pde_mg_day?: number
  found_in_text: boolean
  steps_used?: (string | number)[]
}

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

interface Q3DResult {
  type: 'Q3D'
  text_length: number
  steps_count: number
  elements_found: ElementResult[]
  total_elements: number
  needs_assessment: number
  summary: {
    class_1: number
    class_2a: number
    class_2b: number
    class_3: number
    other: number
  }
  report: string
  llm_used?: boolean
  llm_elements_count?: number
}

interface Q3CResult {
  type: 'Q3C'
  text_length: number
  steps_count: number
  solvents_found: SolventResult[]
  total_solvents: number
  summary: {
    class_1: number
    class_2: number
    class_3: number
    unknown: number
  }
  report: string
  llm_used?: boolean
  llm_solvents_count?: number
  step_analysis?: StepData[]
}

interface CombinedResult {
  id?: string
  q3d: Q3DResult
  q3c: Q3CResult
}

interface HistoryRecord {
  id: string
  filename: string
  llm_used: boolean
  q3c_total: number
  q3d_total: number
  q3d_needs_assessment: number
  created_at: string
}

export function ICHAnalysisPage() {
  const [result, setResult] = useState<CombinedResult | null>(null)
  const [loading, setLoading] = useState(false)

  // History
  const [history, setHistory] = useState<HistoryRecord[]>([])
  const [historyTotal, setHistoryTotal] = useState(0)
  const [historyPage, setHistoryPage] = useState(1)
  const [historyLoading, setHistoryLoading] = useState(false)


  const { message } = App.useApp()


  // Load history
  const loadHistory = useCallback(async (page = 1) => {
    setHistoryLoading(true)
    try {
      const res = await fetch(`/api/v1/research/ich/records?page=${page}&page_size=10`)
      const data = await res.json()
      if (data.code === 200) {
        setHistory(data.data || [])
        setHistoryTotal(data.meta?.total || 0)
        setHistoryPage(page)
      }
    } catch (error) {
      console.error('加载分析历史失败', error)
    } finally {
      setHistoryLoading(false)
    }
  }, [])

  useEffect(() => {
    loadHistory()
  }, [loadHistory])

  // Upload + analyze
  const handleUpload = async (file: File) => {
    setLoading(true)
    try {
      const formData = new FormData()
      formData.append('file', file)

      const res = await fetch(`/api/v1/research/ich/analyze?use_llm=true`, {
        method: 'POST',
        body: formData,
      })

      if (!res.ok) {
        const error = await res.json().catch(() => ({ message: '分析失败' }))
        throw new Error(error.message || '分析失败')
      }

      const data = await res.json()
      setResult({ id: data.data.id, q3c: data.data.q3c_result, q3d: data.data.q3d_result })
      message.success('ICH Q3C/Q3D 杂质识别完成，已保存')
      loadHistory(historyPage)
    } catch (error: any) {
      message.error(error.message || '分析失败')
    } finally {
      setLoading(false)
    }
    return false
  }

  // View a history record
  const viewRecord = async (recordId: string) => {
    setLoading(true)
    try {
      const res = await fetch(`/api/v1/research/ich/records/${recordId}`)
      const data = await res.json()
      if (data.code === 200) {
        setResult({
          id: data.data.id,
          q3d: data.data.q3d_result,
          q3c: data.data.q3c_result,
        })
      }
    } catch (error) {
      message.error('加载记录失败')
    } finally {
      setLoading(false)
    }
  }

  // Delete a history record
  const deleteRecord = async (recordId: string) => {
    try {
      const res = await fetch(`/api/v1/research/ich/records/${recordId}`, { method: 'DELETE' })
      const data = await res.json()
      if (data.code === 200) {
        message.success('记录已删除')
        if (result?.id === recordId) setResult(null)
        loadHistory(historyPage)
      }
    } catch (error) {
      message.error('删除失败')
    }
  }

  // Download report
  const downloadReport = (report: string, filename: string) => {
    const blob = new Blob([report], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  }

  // Q3D element detail card
  const ElementDetailCard = ({ element }: { element: ElementResult }) => {
    const classColor = {
      'Class 1': 'red',
      'Class 2A': 'orange',
      'Class 2B': 'gold',
      'Class 3': 'green',
      'Other': 'default'
    }[element.q3d_class] || 'default'

    const assessmentItems = [
      { route: '口服', assess: element.oral_assess, pde: element.oral_pde },
      { route: '注射', assess: element.parenteral_assess, pde: element.parenteral_pde },
      { route: '吸入', assess: element.inhalation_assess, pde: element.inhalation_pde },
      { route: '皮肤', assess: element.cutaneous_assess, pde: element.cutaneous_pde, ctcl: element.ctcl },
    ]

    return (
      <Card
        size="small"
        title={
          <Space>
            <span style={{ fontSize: 16, fontWeight: 600 }}>{element.symbol}</span>
            <Tag color={classColor}>{element.q3d_class}</Tag>
            {element.intentionally_added && <Tag color="blue">有意添加</Tag>}
          </Space>
        }
        style={{ marginBottom: 8, borderLeft: `3px solid ${element.q3d_class === 'Class 1' ? '#e03131' : element.q3d_class === 'Class 2A' ? '#dd5b00' : '#d9d9d9'}` }}
      >
        <Descriptions size="small" column={2} style={{ marginBottom: 12 }}>
          <Descriptions.Item label="来源" span={2}>{element.source}</Descriptions.Item>
          {element.notes && <Descriptions.Item label="备注" span={2}>{element.notes}</Descriptions.Item>}
        </Descriptions>
        
        <Table
          size="small"
          pagination={false}
          dataSource={assessmentItems}
          rowKey="route"
          columns={[
            { title: '给药途径', dataIndex: 'route', key: 'route', width: 80 },
            {
              title: '是否需要评估',
              dataIndex: 'assess',
              key: 'assess',
              width: 100,
              render: (val: boolean) => val ? <Tag color="warning">需要</Tag> : <Tag color="success">无需</Tag>
            },
            {
              title: 'PDE (μg/天)',
              dataIndex: 'pde',
              key: 'pde',
              width: 100,
              render: (val: number | undefined) => val != null ? val.toFixed(1) : '-'
            },
            {
              title: '备注',
              key: 'note',
              width: 150,
              render: (_: any, record: any) => {
                if (record.ctcl) {
                  return <Text type="secondary" style={{ fontSize: 12 }}>CTCL: {record.ctcl} μg/g</Text>
                }
                return null
              }
            }
          ]}
        />
      </Card>
    )
  }

  // Table columns
  const q3dColumns = [
    { title: '元素', dataIndex: 'symbol', key: 'symbol', width: 80, fixed: 'left' as const },
    {
      title: '分类', dataIndex: 'q3d_class', key: 'q3d_class', width: 100,
      render: (cls: string) => {
        const colors: Record<string, string> = { 'Class 1': 'red', 'Class 2A': 'orange', 'Class 2B': 'gold', 'Class 3': 'green' }
        return <Tag color={colors[cls] || 'default'}>{cls}</Tag>
      },
    },
    { title: '来源', dataIndex: 'source', key: 'source', width: 200 },
    { title: '有意添加', dataIndex: 'intentionally_added', key: 'intentionally_added', width: 100, render: (val: boolean) => val ? <Tag color="blue">是</Tag> : <Tag>否</Tag> },
    { title: '文中发现', dataIndex: 'found_in_text', key: 'found_in_text', width: 100, render: (val: boolean) => val ? <Tag color="success">✓</Tag> : <Tag>-</Tag> },
    { title: '需评估', dataIndex: 'needs_assessment', key: 'needs_assessment', width: 100, render: (val: boolean) => val ? <Tag color="warning">需要</Tag> : <Tag color="success">无需</Tag> },
    { title: '备注', dataIndex: 'notes', key: 'notes', width: 200 },
  ]

  const historyColumns = [
    { title: '文件名', dataIndex: 'filename', key: 'filename', ellipsis: true },
    { title: 'Q3D 元素', dataIndex: 'q3d_total', key: 'q3d_total', width: 100 },
    { title: '需评估', dataIndex: 'q3d_needs_assessment', key: 'q3d_needs_assessment', width: 90, render: (v: number) => v > 0 ? <Tag color="warning">{v}</Tag> : <Tag color="success">0</Tag> },
    { title: 'Q3C 溶剂', dataIndex: 'q3c_total', key: 'q3c_total', width: 100 },
    { title: '时间', dataIndex: 'created_at', key: 'created_at', width: 170, render: (v: string) => v ? new Date(v).toLocaleString('zh-CN') : '-' },
    {
      title: '操作', key: 'action', width: 120,
      render: (_: any, record: HistoryRecord) => (
        <Space size="small">
          <Button type="link" size="small" icon={<EyeOutlined />} onClick={() => viewRecord(record.id)}>查看</Button>
          <Popconfirm title="确定删除此记录？" onConfirm={() => deleteRecord(record.id)}>
            <Button type="link" size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  // Count Q3D alerts - only elements actually found in text
  const q3dClass1Found = result?.q3d?.elements_found.filter(
    e => e.q3d_class === 'Class 1' && e.found_in_text
  ).map(e => e.symbol) || []

  // Count Class 2B intentionally added for compliance alerts
  const q3dClass2BIntentionalCount = result?.q3d?.elements_found.filter(
    e => e.q3d_class === 'Class 2B' && e.intentionally_added
  ).length || 0

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h1 style={{ fontSize: 22, fontWeight: 600, margin: 0 }}>ICH Q3C/Q3D 杂质识别</h1>
        <Space>
          <Upload
            accept=".docx,.doc"
            showUploadList={false}
            beforeUpload={handleUpload}
            disabled={loading}
          >
            <Button type="primary" icon={<UploadOutlined />} loading={loading}>
              上传工艺文件
            </Button>
          </Upload>
        </Space>
      </div>

      {result && (
        <Card style={{ marginBottom: 16 }}>
          <ComplianceAlert
            q3cClass1Count={result?.q3c?.summary.class_1}
            q3cUnknownCount={result?.q3c?.summary.unknown}
            q3dClass1Found={q3dClass1Found}
            q3dClass2BIntentionalCount={q3dClass2BIntentionalCount}
          />
          
          <Tabs
            items={[
              {
                key: 'q3d',
                label: `Q3D 元素杂质 (${result?.q3d?.total_elements} 个)`,
                children: (
                  <div>
                    <Descriptions bordered size="small" column={4} style={{ marginBottom: 16 }}>
                      <Descriptions.Item label="Class 1 元素（高毒）"><Tag color="red">{result?.q3d?.summary.class_1} 个</Tag></Descriptions.Item>
                      <Descriptions.Item label="Class 2A 元素"><Tag color="orange">{result?.q3d?.summary.class_2a} 个</Tag></Descriptions.Item>
                      <Descriptions.Item label="Class 2B 元素"><Tag color="gold">{result?.q3d?.summary.class_2b} 个</Tag></Descriptions.Item>
                      <Descriptions.Item label="Class 3 元素"><Tag color="green">{result?.q3d?.summary.class_3} 个</Tag></Descriptions.Item>
                    </Descriptions>
                    
                    <Collapse
                      style={{ marginBottom: 16 }}
                      defaultActiveKey={['summary']}
                      items={[
                        {
                          key: 'summary',
                          label: <span><ExperimentOutlined style={{ marginRight: 8 }} />元素汇总表</span>,
                          children: (
                            <Table 
                              columns={q3dColumns} 
                              dataSource={result?.q3d?.elements_found} 
                              rowKey="symbol" 
                              pagination={false} 
                              scroll={{ x: 1000 }} 
                              size="small" 
                            />
                          )
                        },
                        {
                          key: 'details',
                          label: <span>元素详细信息（PDE 与评估）</span>,
                          children: (
                            <div>
                              {result?.q3d?.elements_found.map(elem => (
                                <ElementDetailCard key={elem.symbol} element={elem} />
                              ))}
                            </div>
                          )
                        }
                      ]}
                    />
                    
                    <div style={{ marginTop: 16, textAlign: 'center' }}>
                      <Button icon={<DownloadOutlined />} onClick={() => downloadReport(result?.q3d?.report, 'ICH_Q3D_Report.md')}>
                        下载 Q3D 报告
                      </Button>
                    </div>
                  </div>
                ),
              },
              {
                key: 'q3c',
                label: `Q3C 溶剂残留 (${result?.q3c?.total_solvents} 个)`,
                children: (
                  <div>
                    <Descriptions bordered size="small" column={4} style={{ marginBottom: 16 }}>
                      <Descriptions.Item label="Class 1 溶剂（应避免）"><Tag color="red">{result?.q3c?.summary.class_1} 个</Tag></Descriptions.Item>
                      <Descriptions.Item label="Class 2 溶剂（限制使用）"><Tag color="orange">{result?.q3c?.summary.class_2} 个</Tag></Descriptions.Item>
                      <Descriptions.Item label="Class 3 溶剂（低毒）"><Tag color="green">{result?.q3c?.summary.class_3} 个</Tag></Descriptions.Item>
                      <Descriptions.Item label="未列出"><Tag>{result?.q3c?.summary.unknown} 个</Tag></Descriptions.Item>
                    </Descriptions>

                    {result?.q3c?.step_analysis && result?.q3c?.step_analysis.length > 0 && (
                      <StepGroupCard steps={result?.q3c?.step_analysis} />
                    )}

                    <ControlStrategy solvents={result?.q3c?.solvents_found} />
                    
                    <TestingRecommendations solvents={result?.q3c?.solvents_found} />

                    <div style={{ marginTop: 16, textAlign: 'center' }}>
                      <Button icon={<DownloadOutlined />} onClick={() => downloadReport(result?.q3c?.report, 'ICH_Q3C_Report.md')}>
                        下载 Q3C 报告
                      </Button>
                    </div>
                  </div>
                ),
              },
            ]}
          />
        </Card>
      )}

      {/* History */}
      <Card title={<span><HistoryOutlined /> 分析历史</span>}>
        <Table
          columns={historyColumns}
          dataSource={history}
          rowKey="id"
          loading={historyLoading}
          size="small"
          pagination={{
            current: historyPage,
            pageSize: 10,
            total: historyTotal,
            onChange: (page) => loadHistory(page),
            showTotal: (total) => `共 ${total} 条记录`,
          }}
        />
      </Card>

    </div>
  )
}
