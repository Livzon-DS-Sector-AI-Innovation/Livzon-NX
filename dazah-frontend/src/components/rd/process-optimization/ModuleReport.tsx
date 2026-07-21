'use client'

import { useState } from 'react'
import { Card, Button, Space, Tag, Divider, Row, Col, Descriptions, Table, App, Modal, Input } from 'antd'
import { CheckCircleOutlined, DownloadOutlined, EditOutlined, SendOutlined, FileTextOutlined } from '@ant-design/icons'
import type {
  LabConfirmationStudy,
  DOEExperiment,
  ImpurityStudy,
  CrystalFormStudy,
  QualityStandardSet,
  ScaleUpStudy,
} from '@/types/rd'

import { generateFullReport, type ReportMetadata } from '@/lib/report-templates'
interface ModuleReportProps {
  optimizationId: string
  optimizationName: string
  doeExperiment?: DOEExperiment
  impurityStudy?: ImpurityStudy
  crystalFormStudy?: CrystalFormStudy
  qualityStandardSet?: QualityStandardSet
  labConfirmationStudy?: LabConfirmationStudy
  scaleUpStudy?: ScaleUpStudy
  onComplete: () => void
}

export function ModuleReport({
  optimizationId,
  optimizationName,
  doeExperiment,
  impurityStudy,
  crystalFormStudy,
  qualityStandardSet,
  labConfirmationStudy,
  scaleUpStudy,
  onComplete,
}: ModuleReportProps) {
  const { message } = App.useApp()
  const now = new Date()
  const reportNo = `PO-${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}-${String(now.getHours()).padStart(2, '0')}${String(now.getMinutes()).padStart(2, '0')}`
  const reportTime = now.toLocaleString('zh-CN')

  const [isEditing, setIsEditing] = useState(false)
  const [editContent, setEditContent] = useState('')

  const handleConfirm = () => {
    message.success('工艺优化已完成，报告已生成')
    onComplete()
  }

  const handleDownload = () => {
    const metadata: ReportMetadata = {
      reportNo,
      reportTime,
      optimizationName,
    }

    const md = generateFullReport(metadata, {
      doeExperiment,
      impurityStudy,
      crystalFormStudy,
      qualityStandardSet,
      labConfirmationStudy,
      scaleUpStudy,
    })

    const blob = new Blob([md], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `工艺优化报告_${reportNo}.md`
    a.click()
    URL.revokeObjectURL(url)
    message.success('报告已下载')
  }

  const handleEdit = () => {
    setEditContent(`# ${optimizationName} - 工艺优化报告\n\n请在此编辑报告内容...`)
    setIsEditing(true)
  }

  const handleSaveEdit = () => {
    setIsEditing(false)
    message.success('修改已保存')
  }

  const handleSubmit = () => {
    message.success('报告已提交审核')
    onComplete()
  }

  const modules = [
    { name: 'DOE实验设计', done: !!doeExperiment, detail: doeExperiment ? `${doeExperiment.factors.length}因素, ${doeExperiment.runs.filter(r => r.status === 'completed').length}组完成, R²=${doeExperiment.analysis_result?.r_squared || '-'}` : '' },
    { name: '杂质研究', done: !!impurityStudy, detail: impurityStudy ? `${impurityStudy.impurities.length}种杂质` : '' },
    { name: '晶型研究', done: !!crystalFormStudy, detail: crystalFormStudy ? `${crystalFormStudy.records.length}种晶型` : '' },
    { name: '质量标准', done: !!qualityStandardSet, detail: qualityStandardSet ? `${qualityStandardSet.standards.length}项指标` : '' },
    { name: '公斤级放大', done: !!scaleUpStudy, detail: scaleUpStudy ? `${scaleUpStudy.batch ? 1 : 0}批, 目标${scaleUpStudy.target_scale_kg}kg` : '' },
  ]

  return (
    <div>
      <Card
        title={
          <Space>
            <FileTextOutlined />
            <span>工艺优化报告</span>
            <Tag color="blue">{reportNo}</Tag>
          </Space>
        }
      >
        {/* 报告概览 */}
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontWeight: 600, marginBottom: 12 }}>📋 报告内容概览</div>
          <Row gutter={16}>
            {modules.map((m, i) => (
              <Col span={4} key={i} style={{ textAlign: 'center' }}>
                <Card size="small" style={{ border: m.done ? '1px solid #52c41a' : '1px dashed #d9d9d9' }}>
                  <div style={{ fontSize: 24 }}>{m.done ? '✅' : '⬜'}</div>
                  <div style={{ fontWeight: 500, marginTop: 4 }}>{m.name}</div>
                  <div style={{ fontSize: 12, color: '#999', marginTop: 4 }}>{m.detail || '未完成'}</div>
                </Card>
              </Col>
            ))}
          </Row>
        </div>

        <Divider />

        {/* 报告目录 */}
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontWeight: 600, marginBottom: 8 }}>📑 报告目录</div>
          <Card size="small">
            <ol style={{ margin: 0, paddingLeft: 20, lineHeight: 2 }}>
              <li>项目概述与优化目标</li>
              <li>DOE实验设计与分析结果
                {doeExperiment?.analysis_result && <Tag color="green" style={{ marginLeft: 8 }}>R²={doeExperiment.analysis_result.r_squared}</Tag>}
              </li>
              <li>杂质研究与控制策略
                {impurityStudy && <Tag color="blue" style={{ marginLeft: 8 }}>{impurityStudy.impurities.length}种杂质</Tag>}
              </li>
              <li>晶型筛选与研究结果
                {crystalFormStudy?.preferred_form && <Tag color="purple" style={{ marginLeft: 8 }}>推荐: {crystalFormStudy.preferred_form.form_name}</Tag>}
              </li>
              <li>质量标准草案
                {qualityStandardSet && <Tag color="orange" style={{ marginLeft: 8 }}>{qualityStandardSet.standards.length}项</Tag>}
              </li>
              <li>公斤级放大试验
                {scaleUpStudy && <Tag color="cyan" style={{ marginLeft: 8 }}>{scaleUpStudy.batch ? 1 : 0}批</Tag>}
              </li>
              <li>综合结论与建议</li>
              <li>附录（图谱、数据表）</li>
            </ol>
          </Card>
        </div>

        <Divider />

        {/* 可下载附件 */}
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontWeight: 600, marginBottom: 8 }}>📎 可下载附件</div>
          <Space orientation="vertical" style={{ width: '100%' }}>
            {[
              { name: '工艺优化报告.md', icon: '📄' },
              { name: 'DOE实验数据.xlsx', icon: '📊' },
              { name: '杂质研究汇总.xlsx', icon: '📋' },
              { name: '晶型筛选报告.md', icon: '🔬' },
              { name: '质量标准草案.md', icon: '📏' },
              { name: '公斤级放大数据.xlsx', icon: '📈' },
            ].map((file, i) => (
              <div key={i} style={{ padding: '10px 12px', backgroundColor: '#fafafa', borderRadius: 4, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span>{file.icon} {file.name}</span>
                <Button size="small" icon={<DownloadOutlined />} onClick={handleDownload}>下载</Button>
              </div>
            ))}
          </Space>
        </div>

        <Divider />

        <Space>
          <Button icon={<DownloadOutlined />} onClick={handleDownload}>📄 下载报告</Button>
          <Button icon={<EditOutlined />} onClick={handleEdit}>✏️ 在线编辑</Button>
          <Button icon={<SendOutlined />} type="primary" onClick={handleSubmit}>📤 提交审核</Button>
        </Space>
      </Card>

      <Card>
        <Space>
          <Button type="primary" icon={<CheckCircleOutlined />} onClick={handleConfirm} size="large">
            ✅ 确认完成工艺优化
          </Button>
        </Space>
      </Card>

      <Modal
        title="在线编辑报告"
        open={isEditing}
        onCancel={() => setIsEditing(false)}
        onOk={handleSaveEdit}
        width={800}
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
    </div>
  )
}
