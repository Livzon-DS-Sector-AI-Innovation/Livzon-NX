'use client'

import { useState } from 'react'

import { Card, Button, Space, Tag, Divider, Row, Col, Descriptions, Table, App, Modal, Input } from 'antd'
import { CheckCircleOutlined, DownloadOutlined, EditOutlined, SendOutlined, FileTextOutlined } from '@ant-design/icons'
import type { DimensionAssessment, ExperimentRecord, CandidateRoute } from '@/types/rd'

interface ModuleConfirmationProps {
  routeId: string
  selectedRouteName: string
  assessmentScore: number
  assessment?: DimensionAssessment
  experiments?: ExperimentRecord[]
  selectedRoutes?: CandidateRoute[]
  literatureSource?: string
  onComplete: () => void
}

export function ModuleConfirmation({
  routeId,
  selectedRouteName,
  assessmentScore,
  assessment,
  experiments = [],
  selectedRoutes = [],
  literatureSource = '',
  onComplete
}: ModuleConfirmationProps) {
  const { message } = App.useApp()
  const now = new Date()
  const reportNo = `RD-${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}-${String(now.getHours()).padStart(2, '0')}${String(now.getMinutes()).padStart(2, '0')}`
  const reportTime = now.toLocaleString('zh-CN')

  const handleConfirm = () => {
    message.success('路线已确认，报告已生成')
    onComplete()
  }

  const handleDownload = () => {
    const report = {
      title: '工艺路线确认报告',
      route_no: routeId,
      route_name: selectedRouteName,
      assessment_score: assessmentScore,
      generated_at: reportTime,
      assessment: assessment ? {
        weights: assessment.weights,
        scores: assessment.scores,
        weighted_total: assessment.weighted_total,
        notes: assessment.notes,
      } : null,
      experiments: experiments.map(e => ({
        no: e.experiment_no,
        title: e.title,
        date: e.date,
        yield: e.yield,
        purity: e.purity,
        status: e.status,
        summary: e.result_summary,
      })),
      selected_routes: selectedRoutes.map(r => ({
        name: r.name,
        steps: r.steps,
        total_yield: r.total_yield,
        is_recommended: r.is_recommended,
      })),
    }
    
    let md = `# 工艺路线确认报告\n\n`
    md += `**报告编号：** ${reportNo}\n`
    md += `**生成时间：** ${reportTime}\n\n`
    md += `## 基本信息\n\n`
    md += `- **路线编号：** ${routeId}\n`
    md += `- **路线名称：** ${selectedRouteName}\n`
    md += `- **综合评分：** ${assessmentScore}\n\n`
    if (assessment) {
      md += `## 四维度评估\n\n`
      md += `| 维度 | 得分 | 权重 |\n`
      md += `|------|------|------|\n`
      md += `| 安全性 | ${assessment.scores.safety} | ${assessment.weights.safety}% |\n`
      md += `| 环保性 | ${assessment.scores.environmental} | ${assessment.weights.environmental}% |\n`
      md += `| 成本 | ${assessment.scores.cost} | ${assessment.weights.cost}% |\n`
      md += `| 可行性 | ${assessment.scores.feasibility} | ${assessment.weights.feasibility}% |\n\n`
      md += `### 评估详情\n\n`
      md += `**安全性：** ${assessment.notes.safety}\n\n`
      md += `**环保性：** ${assessment.notes.environmental}\n\n`
      md += `**成本：** ${assessment.notes.cost}\n\n`
      md += `**可行性：** ${assessment.notes.feasibility}\n\n`
    }
    md += `## 实验记录汇总\n\n`
    md += `共 ${experiments.length} 条实验记录\n\n`
    if (experiments.length > 0) {
      md += `| 编号 | 标题 | 日期 | 收率 | 纯度 | 状态 |\n`
      md += `|------|------|------|------|------|------|\n`
      experiments.forEach(e => {
        md += `| ${e.experiment_no} | ${e.title} | ${e.date} | ${e.yield || '-'}% | ${e.purity || '-'}% | ${e.status} |\n`
      })
      md += `\n`
    }
    md += `## 候选路线对比\n\n`
    if (selectedRoutes.length > 0) {
      md += `| 路线 | 步骤数 | 总收率 | 推荐 |\n`
      md += `|------|--------|--------|------|\n`
      selectedRoutes.forEach(r => {
        md += `| ${r.name} | ${r.steps} | ${r.total_yield}% | ${r.is_recommended ? '✓' : ''} |\n`
      })
    }
    
    const blob = new Blob([md], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `工艺路线确认报告_${reportNo}.md`
    a.click()
    URL.revokeObjectURL(url)
    message.success('报告已下载')
  }

  const [isEditing, setIsEditing] = useState(false)
  const [editContent, setEditContent] = useState('')

  const handleEdit = () => {
    const report = {
      route_name: selectedRouteName,
      assessment_score: assessmentScore,
      recommendation: assessment?.notes.safety || '',
      experiments_count: experiments.length,
    }
    setEditContent(JSON.stringify(report, null, 2))
    setIsEditing(true)
  }

  const handleSaveEdit = () => {
    try {
      JSON.parse(editContent)
      setIsEditing(false)
      message.success('修改已保存')
    } catch {
      message.error('JSON格式错误，请检查')
    }
  }

  const handleSubmit = () => {
    message.success('报告已提交审核')
  }

  const experimentColumns = [
    { title: '编号', dataIndex: 'experiment_no', key: 'experiment_no', width: 120 },
    { title: '标题', dataIndex: 'title', key: 'title', width: 180 },
    { title: '日期', dataIndex: 'date', key: 'date', width: 100 },
    { title: '收率', dataIndex: 'yield', key: 'yield', width: 70, render: (v: number) => v ? `${v}%` : '-' },
    { title: '纯度', dataIndex: 'purity', key: 'purity', width: 70, render: (v: number) => v ? `${v}%` : '-' },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 80,
      render: (s: string) => {
        const map: Record<string, { color: string; label: string }> = {
          completed: { color: 'success', label: '完成' },
          in_progress: { color: 'processing', label: '进行中' },
          failed: { color: 'error', label: '失败' },
          planned: { color: 'default', label: '计划' },
        }
        return <Tag color={map[s]?.color}>{map[s]?.label}</Tag>
      }
    },
  ]

  const completedExps = experiments.filter(e => e.status === 'completed')
  const avgYield = completedExps.length > 0
    ? Math.round(completedExps.reduce((sum, e) => sum + (e.yield || 0), 0) / completedExps.length)
    : 0
  const avgPurity = completedExps.length > 0
    ? Math.round(completedExps.reduce((sum, e) => sum + (e.purity || 0), 0) / completedExps.length * 10) / 10
    : 0

  return (
    <div>
      <Modal
        title="编辑报告"
        open={isEditing}
        onOk={handleSaveEdit}
        onCancel={() => setIsEditing(false)}
        width={700}
        okText="保存"
        cancelText="取消"
      >
        <Input.TextArea
          rows={20}
          value={editContent}
          onChange={(e) => setEditContent(e.target.value)}
          style={{ fontFamily: 'monospace', fontSize: 13 }}
        />
      </Modal>

      <Card title="📄 工艺路线确认报告" style={{ marginBottom: 16 }}>
        <Card size="small" style={{ marginBottom: 16, backgroundColor: '#fafafa' }}>
          <Descriptions column={2} size="small">
            <Descriptions.Item label="报告编号">{reportNo}</Descriptions.Item>
            <Descriptions.Item label="生成时间">{reportTime}</Descriptions.Item>
            <Descriptions.Item label="文献来源">{literatureSource || '-'}</Descriptions.Item>
            <Descriptions.Item label="候选路线数">{selectedRoutes.length}条</Descriptions.Item>
          </Descriptions>
        </Card>

        <Card size="small" style={{ marginBottom: 16, borderColor: '#52c41a' }}>
          <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>
            ✅ 推荐：{selectedRouteName}（加权综合评分 {assessmentScore}）
          </div>

          {assessment && (
            <Row gutter={16} style={{ marginBottom: 16 }}>
              <Col span={6}>
                <div style={{ textAlign: 'center', padding: 12, background: '#fff1f0', borderRadius: 8 }}>
                  <div style={{ fontSize: 24, fontWeight: 600, color: '#ff4d4f' }}>{assessment.scores.safety}</div>
                  <div style={{ fontSize: 12, color: '#666' }}>安全性 ({assessment.weights.safety}%)</div>
                </div>
              </Col>
              <Col span={6}>
                <div style={{ textAlign: 'center', padding: 12, background: '#f6ffed', borderRadius: 8 }}>
                  <div style={{ fontSize: 24, fontWeight: 600, color: '#52c41a' }}>{assessment.scores.environmental}</div>
                  <div style={{ fontSize: 12, color: '#666' }}>环保性 ({assessment.weights.environmental}%)</div>
                </div>
              </Col>
              <Col span={6}>
                <div style={{ textAlign: 'center', padding: 12, background: '#fffbe6', borderRadius: 8 }}>
                  <div style={{ fontSize: 24, fontWeight: 600, color: '#faad14' }}>{assessment.scores.cost}</div>
                  <div style={{ fontSize: 12, color: '#666' }}>成本 ({assessment.weights.cost}%)</div>
                </div>
              </Col>
              <Col span={6}>
                <div style={{ textAlign: 'center', padding: 12, background: '#e6f7ff', borderRadius: 8 }}>
                  <div style={{ fontSize: 24, fontWeight: 600, color: '#1890ff' }}>{assessment.scores.feasibility}</div>
                  <div style={{ fontSize: 12, color: '#666' }}>可行性 ({assessment.weights.feasibility}%)</div>
                </div>
              </Col>
            </Row>
          )}

          <div style={{ marginBottom: 8 }}><b>推荐理由：</b></div>
          <ul style={{ margin: 0, paddingLeft: 20, lineHeight: 2 }}>
            {assessment ? (
              <>
                <li>安全性评分{assessment.scores.safety}分 — {assessment.notes.safety.slice(0, 50)}...</li>
                <li>环保性评分{assessment.scores.environmental}分 — {assessment.notes.environmental.slice(0, 50)}...</li>
                <li>成本评分{assessment.scores.cost}分 — {assessment.notes.cost.slice(0, 50)}...</li>
                <li>可行性评分{assessment.scores.feasibility}分 — {assessment.notes.feasibility.slice(0, 50)}...</li>
              </>
            ) : (
              <>
                <li>综合评分最优</li>
                <li>原料易得，供应链稳定</li>
                <li>放大风险可控，适合公斤级生产</li>
              </>
            )}
          </ul>
        </Card>

        {selectedRoutes.length > 1 && (
          <Card size="small" title="📊 候选路线对比" style={{ marginBottom: 16 }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: '2px solid #f0f0f0' }}>
                  <th style={{ textAlign: 'left', padding: '8px 12px' }}>路线</th>
                  <th style={{ textAlign: 'center', padding: '8px 12px' }}>步骤数</th>
                  <th style={{ textAlign: 'center', padding: '8px 12px' }}>总收率</th>
                  <th style={{ textAlign: 'left', padding: '8px 12px' }}>关键步骤</th>
                  <th style={{ textAlign: 'center', padding: '8px 12px' }}>推荐</th>
                </tr>
              </thead>
              <tbody>
                {selectedRoutes.map((route, idx) => (
                  <tr key={route.id} style={{ borderBottom: '1px solid #f0f0f0', background: idx === 0 ? '#f6ffed' : 'transparent' }}>
                    <td style={{ padding: '8px 12px' }}><b>{route.name}</b></td>
                    <td style={{ textAlign: 'center', padding: '8px 12px' }}>{route.steps}步</td>
                    <td style={{ textAlign: 'center', padding: '8px 12px' }}>{route.total_yield}%</td>
                    <td style={{ padding: '8px 12px', fontSize: 12 }}>{route.key_step}</td>
                    <td style={{ textAlign: 'center', padding: '8px 12px' }}>
                      {route.is_recommended && <Tag color="blue">推荐</Tag>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )}

        {experiments.length > 0 && (
          <Card size="small" title={`🧪 实验记录汇总（${experiments.length}条）`} style={{ marginBottom: 16 }}>
            <Row gutter={16} style={{ marginBottom: 16 }}>
              <Col span={8}>
                <Card size="small" style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: 24, fontWeight: 600, color: '#1890ff' }}>{experiments.length}</div>
                  <div style={{ fontSize: 12, color: '#999' }}>总实验数</div>
                </Card>
              </Col>
              <Col span={8}>
                <Card size="small" style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: 24, fontWeight: 600, color: '#52c41a' }}>{avgYield}%</div>
                  <div style={{ fontSize: 12, color: '#999' }}>平均收率</div>
                </Card>
              </Col>
              <Col span={8}>
                <Card size="small" style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: 24, fontWeight: 600, color: '#722ed1' }}>{avgPurity}%</div>
                  <div style={{ fontSize: 12, color: '#999' }}>平均纯度</div>
                </Card>
              </Col>
            </Row>
            <Table
              columns={experimentColumns}
              dataSource={experiments}
              rowKey="id"
              pagination={false}
              size="small"
            />
          </Card>
        )}

        <div style={{ marginBottom: 16 }}>
          <div style={{ fontWeight: 600, marginBottom: 8 }}>📋 报告内容</div>
          <Card size="small">
            <ol style={{ margin: 0, paddingLeft: 20, lineHeight: 2 }}>
              <li>项目概述</li>
              <li>候选路线对比（{selectedRoutes.length}条）</li>
              <li>四维度评估详情（综合评分 {assessmentScore}）</li>
              <li>推荐路线及理由</li>
              <li>实验记录汇总（{experiments.length}条）</li>
              <li>公斤级放大方案</li>
              <li>风险评估与应对措施</li>
              <li>附录（图谱、物料清单）</li>
            </ol>
          </Card>
        </div>

        <div style={{ marginBottom: 16 }}>
          <div style={{ fontWeight: 600, marginBottom: 8 }}>📎 可下载附件</div>
          <Space orientation="vertical" style={{ width: '100%' }}>
            <div style={{ padding: '10px 12px', backgroundColor: '#fafafa', borderRadius: 4, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span><FileTextOutlined style={{ marginRight: 8 }} />工艺路线确认报告.docx</span>
              <Button size="small" icon={<DownloadOutlined />} onClick={handleDownload}>下载</Button>
            </div>
            <div style={{ padding: '10px 12px', backgroundColor: '#fafafa', borderRadius: 4, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span><FileTextOutlined style={{ marginRight: 8 }} />公斤级放大方案.docx</span>
              <Button size="small" icon={<DownloadOutlined />} onClick={handleDownload}>下载</Button>
            </div>
            <div style={{ padding: '10px 12px', backgroundColor: '#fafafa', borderRadius: 4, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span>📊 四维度评估雷达图.png</span>
              <Button size="small" icon={<DownloadOutlined />} onClick={handleDownload}>下载</Button>
            </div>
            <div style={{ padding: '10px 12px', backgroundColor: '#fafafa', borderRadius: 4, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span>📋 实验记录汇总.xlsx</span>
              <Button size="small" icon={<DownloadOutlined />} onClick={handleDownload}>下载</Button>
            </div>
          </Space>
        </div>

        <Divider />

        <Space>
          <Button icon={<DownloadOutlined />} onClick={handleDownload}>下载报告</Button>
          <Button icon={<EditOutlined />} onClick={handleEdit}>✏️ 在线编辑</Button>
          <Button icon={<SendOutlined />} type="primary" onClick={handleSubmit}>📤 提交审核</Button>
        </Space>
      </Card>

      <Card>
        <Space>
          <Button type="primary" icon={<CheckCircleOutlined />} onClick={handleConfirm} size="large">
            ✅ 确认完成
          </Button>
        </Space>
      </Card>
    </div>
  )
}
