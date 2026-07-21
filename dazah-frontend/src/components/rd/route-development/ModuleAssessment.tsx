'use client'

import { useState, useMemo } from 'react'
import { Card, Slider, Button, Space, Tag, Alert, Select, Row, Col, App } from 'antd'
import { CheckCircleOutlined, ReloadOutlined, FileTextOutlined, DownloadOutlined } from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import type { DimensionAssessment, DimensionWeights, ExperimentRecord } from '@/types/rd'

interface ModuleAssessmentProps {
  routeId: string
  selectedRouteName: string
  experiments?: ExperimentRecord[]
  onComplete: (assessment: DimensionAssessment) => void
}

export function ModuleAssessment({ routeId, selectedRouteName, experiments = [], onComplete }: ModuleAssessmentProps) {
  const { message } = App.useApp()
  const [weights, setWeights] = useState<DimensionWeights>({
    safety: 30,
    environmental: 20,
    cost: 20,
    feasibility: 30,
  })

  const [projectType, setProjectType] = useState('generic')
  const [scale, setScale] = useState('kg')

  const scores = useMemo(() => {
    if (experiments.length === 0) {
      return { safety: 85, environmental: 70, cost: 75, feasibility: 65 }
    }

    const completedExps = experiments.filter(e => e.status === 'completed')
    const avgYield = completedExps.reduce((sum, e) => sum + (e.yield || 0), 0) / (completedExps.length || 1)
    const avgPurity = completedExps.reduce((sum, e) => sum + (e.purity || 0), 0) / (completedExps.length || 1)
    const failedCount = experiments.filter(e => e.status === 'failed').length

    let safetyScore = 85
    if (failedCount > 0) safetyScore -= failedCount * 10
    if (experiments.some(e => e.reaction_temp?.includes('-') || e.reaction_temp?.includes('0°C'))) {
      safetyScore -= 5
    }
    safetyScore = Math.max(40, Math.min(100, safetyScore))

    const environmentalScore = 70 + (avgPurity > 98 ? 10 : 0)
    const costScore = Math.min(95, 50 + avgYield * 0.5)
    const successRate = completedExps.length / (experiments.length || 1)
    const feasibilityScore = Math.round(successRate * 80 + (avgYield > 80 ? 15 : 5))

    return {
      safety: Math.round(safetyScore),
      environmental: Math.round(environmentalScore),
      cost: Math.round(costScore),
      feasibility: Math.round(Math.min(100, feasibilityScore)),
    }
  }, [experiments])

  const weightSum = weights.safety + weights.environmental + weights.cost + weights.feasibility
  const isWeightValid = weightSum === 100

  const weightedTotal = Math.round(
    (scores.safety * weights.safety +
      scores.environmental * weights.environmental +
      scores.cost * weights.cost +
      scores.feasibility * weights.feasibility) / 100
  )

  const radarOption = {
    tooltip: {},
    radar: {
      indicator: [
        { name: '安全性', max: 100 },
        { name: '环保性', max: 100 },
        { name: '成本', max: 100 },
        { name: '可行性', max: 100 },
      ],
      shape: 'circle',
      splitNumber: 5,
      axisName: { color: '#666', fontSize: 13 },
      splitLine: { lineStyle: { color: '#e8e8e8' } },
      splitArea: { areaStyle: { color: ['#fff', '#f5f5f5'] } },
    },
    series: [{
      type: 'radar',
      data: [{
        value: [scores.safety, scores.environmental, scores.cost, scores.feasibility],
        name: '评分',
        areaStyle: { color: 'rgba(24, 144, 255, 0.2)' },
        lineStyle: { color: '#1890ff', width: 2 },
        itemStyle: { color: '#1890ff' },
      }],
    }],
  }

  const handleGenerateReport = () => {
    const report = {
      title: '四维度评估报告',
      route: selectedRouteName,
      date: new Date().toLocaleString('zh-CN'),
      weights,
      scores,
      weighted_total: weightedTotal,
      details: {
        safety: { score: scores.safety, weight: weights.safety, note: getDimensionNote('safety', scores, experiments) },
        environmental: { score: scores.environmental, weight: weights.environmental, note: getDimensionNote('environmental', scores, experiments) },
        cost: { score: scores.cost, weight: weights.cost, note: getDimensionNote('cost', scores, experiments) },
        feasibility: { score: scores.feasibility, weight: weights.feasibility, note: getDimensionNote('feasibility', scores, experiments) },
      },
      conclusion: weightedTotal >= 80 ? '优秀 - 推荐采用' : weightedTotal >= 60 ? '良好 - 可以实施' : weightedTotal >= 40 ? '一般 - 需要优化' : '较差 - 建议重新评估',
    }
    
    let md = `# 四维度评估报告\n\n`
    md += `**评估路线：** ${selectedRouteName}\n`
    md += `**评估时间：** ${new Date().toLocaleString('zh-CN')}\n\n`
    md += `## 综合评分\n\n`
    md += `**加权总分：** ${weightedTotal} / 100\n\n`
    md += `## 权重设置\n\n`
    md += `| 维度 | 权重 |\n`
    md += `|------|------|\n`
    md += `| 安全性 | ${weights.safety}% |\n`
    md += `| 环保性 | ${weights.environmental}% |\n`
    md += `| 成本 | ${weights.cost}% |\n`
    md += `| 可行性 | ${weights.feasibility}% |\n\n`
    md += `## 各维度评分\n\n`
    md += `| 维度 | 得分 | 权重 | 加权得分 |\n`
    md += `|------|------|------|----------|\n`
    md += `| 安全性 | ${scores.safety} | ${weights.safety}% | ${Math.round(scores.safety * weights.safety / 100)} |\n`
    md += `| 环保性 | ${scores.environmental} | ${weights.environmental}% | ${Math.round(scores.environmental * weights.environmental / 100)} |\n`
    md += `| 成本 | ${scores.cost} | ${weights.cost}% | ${Math.round(scores.cost * weights.cost / 100)} |\n`
    md += `| 可行性 | ${scores.feasibility} | ${weights.feasibility}% | ${Math.round(scores.feasibility * weights.feasibility / 100)} |\n\n`
    md += `## 详细评估\n\n`
    md += `### 安全性（${scores.safety}分）\n\n${getDimensionNote('safety', scores, experiments)}\n\n`
    md += `### 环保性（${scores.environmental}分）\n\n${getDimensionNote('environmental', scores, experiments)}\n\n`
    md += `### 成本（${scores.cost}分）\n\n${getDimensionNote('cost', scores, experiments)}\n\n`
    md += `### 可行性（${scores.feasibility}分）\n\n${getDimensionNote('feasibility', scores, experiments)}\n\n`
    md += `## 结论\n\n`
    md += weightedTotal >= 80 ? '**优秀** - 推荐采用' : weightedTotal >= 60 ? '**良好** - 可以实施' : weightedTotal >= 40 ? '**一般** - 需要优化' : '**较差** - 建议重新评估'
    
    const blob = new Blob([md], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `四维度评估报告_${new Date().toISOString().split('T')[0]}.md`
    a.click()
    URL.revokeObjectURL(url)
    message.success('评估报告已下载')
  }

  const handleReassess = () => {
    // 重置权重到默认值
    setWeights({ safety: 30, environmental: 20, cost: 20, feasibility: 30 })
    message.info('已重置评估参数，请重新调整权重')
  }

  const handleConfirm = () => {
    if (!isWeightValid) {
      message.error(`权重总和必须为100%，当前为${weightSum}%`)
      return
    }
    const assessment: DimensionAssessment = {
      weights,
      scores,
      weighted_total: weightedTotal,
      notes: {
        safety: generateSafetyNote(experiments, scores.safety),
        environmental: generateEnvironmentalNote(scores.environmental),
        cost: generateCostNote(scores.cost, experiments),
        feasibility: generateFeasibilityNote(scores.feasibility, experiments),
      },
    }
    onComplete(assessment)
    message.success('评估完成，进入路线确认阶段')
  }

  const handleResetWeights = () => {
    if (projectType === 'generic') {
      setWeights({ safety: 30, environmental: 20, cost: 20, feasibility: 30 })
    } else if (projectType === 'improved') {
      setWeights({ safety: 35, environmental: 25, cost: 15, feasibility: 25 })
    } else {
      setWeights({ safety: 25, environmental: 25, cost: 30, feasibility: 20 })
    }
    message.info('已重置为推荐权重')
  }

  const dimensionConfig = [
    { key: 'safety' as const, label: '安全性', color: '#ff4d4f', icon: '🔴', desc: 'MTSR、TD24、反应热分析' },
    { key: 'environmental' as const, label: '环保性', color: '#52c41a', icon: '🟢', desc: 'E因子、溶剂回收率' },
    { key: 'cost' as const, label: '成本', color: '#faad14', icon: '🟡', desc: '原料成本、关键物料' },
    { key: 'feasibility' as const, label: '可行性', color: '#1890ff', icon: '🔵', desc: '操作难度、放大风险' },
  ]

  return (
    <div>
      <Card title={`📊 四维度评估 — ${selectedRouteName}`} style={{ marginBottom: 16 }}>
        <Alert
          title="动态权重设置"
          description="根据项目特点调整各维度权重，权重总和必须为100%"
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
        />

        <Row gutter={16} style={{ marginBottom: 24 }}>
          <Col span={12}>
            <div style={{ fontWeight: 500, marginBottom: 8 }}>项目类型</div>
            <Select value={projectType} onChange={setProjectType} style={{ width: '100%' }} options={[
              { value: 'generic', label: '仿制药' },
              { value: 'improved', label: '改良型新药' },
              { value: 'intermediate', label: '原料药中间体' },
            ]} />
          </Col>
          <Col span={12}>
            <div style={{ fontWeight: 500, marginBottom: 8 }}>生产规模</div>
            <Select value={scale} onChange={setScale} style={{ width: '100%' }} options={[
              { value: 'kg', label: '公斤级' },
              { value: '10kg', label: '十公斤级' },
              { value: '100kg', label: '百公斤级' },
            ]} />
          </Col>
        </Row>

        <Row gutter={24}>
          <Col span={14}>
            <div style={{ fontWeight: 500, marginBottom: 16 }}>权重调整</div>
            {dimensionConfig.map((dim) => (
              <div key={dim.key} style={{ marginBottom: 16 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                  <span>
                    {dim.icon} <b>{dim.label}</b>
                    <span style={{ color: '#999', fontSize: 12, marginLeft: 8 }}>{dim.desc}</span>
                  </span>
                  <span style={{ fontWeight: 600, color: dim.color }}>{weights[dim.key]}%</span>
                </div>
                <Slider
                  min={0}
                  max={50}
                  value={weights[dim.key]}
                  onChange={(v) => setWeights({ ...weights, [dim.key]: v })}
                  styles={{ track: { backgroundColor: dim.color } }}
                />
              </div>
            ))}
            <Alert
              title={isWeightValid ? '权重总和正确' : `权重总和为${weightSum}%，需要调整为100%`}
              type={isWeightValid ? 'success' : 'warning'}
              showIcon
              style={{ marginTop: 8 }}
              action={<Button size="small" onClick={handleResetWeights}>重置</Button>}
            />
          </Col>
          <Col span={10}>
            <div style={{ fontWeight: 500, marginBottom: 16 }}>评估雷达图</div>
            <ReactECharts option={radarOption} style={{ height: 280 }} />
          </Col>
        </Row>

        <Card size="small" style={{ marginTop: 16, textAlign: 'center', background: 'linear-gradient(135deg, #f0f5ff 0%, #e6f7ff 100%)' }}>
          <div style={{ fontSize: 56, fontWeight: 700, color: weightedTotal >= 70 ? '#52c41a' : weightedTotal >= 50 ? '#faad14' : '#ff4d4f' }}>
            {weightedTotal}
          </div>
          <div style={{ fontSize: 14, color: '#666' }}>加权综合评分 / 100</div>
          <div style={{ marginTop: 16, display: 'flex', justifyContent: 'center', gap: 40 }}>
            {dimensionConfig.map((dim) => (
              <div key={dim.key}>
                <div style={{ fontSize: 28, fontWeight: 600, color: dim.color }}>{scores[dim.key]}</div>
                <div style={{ fontSize: 12, color: '#999' }}>{dim.label} ({weights[dim.key]}%)</div>
              </div>
            ))}
          </div>
        </Card>

        <div style={{ marginTop: 16 }}>
          <div style={{ fontWeight: 500, marginBottom: 12 }}>📝 评估详情</div>
          {dimensionConfig.map((dim) => (
            <Card key={dim.key} size="small" style={{ marginBottom: 8 }}>
              <div style={{ fontWeight: 600, marginBottom: 8 }}>
                {dim.icon} {dim.label}（{scores[dim.key]}分，权重{weights[dim.key]}%）
              </div>
              <div style={{ fontSize: 13, color: '#555', lineHeight: 1.8, whiteSpace: 'pre-line' }}>
                {getDimensionNote(dim.key, scores, experiments)}
              </div>
            </Card>
          ))}
        </div>
      </Card>

      <Card>
        <Space>
          <Button type="primary" icon={<CheckCircleOutlined />} onClick={handleConfirm} size="large" disabled={!isWeightValid}>
            ✅ 确认并进入下一步（路线确认）
          </Button>
          <Button icon={<ReloadOutlined />} onClick={handleReassess}>🔄 重新评估</Button>
          <Button icon={<DownloadOutlined />} onClick={handleGenerateReport}>📄 下载评估报告</Button>
        </Space>
      </Card>
    </div>
  )
}

function getDimensionNote(key: string, scores: Record<string, number>, experiments: ExperimentRecord[]): string {
  const completedExps = experiments.filter(e => e.status === 'completed')
  const avgYield = completedExps.length > 0
    ? Math.round(completedExps.reduce((sum, e) => sum + (e.yield || 0), 0) / completedExps.length)
    : 0
  switch (key) {
    case 'safety':
      return `• 安全性评分: ${scores.safety}分\n• 实验失败次数: ${experiments.filter(e => e.status === 'failed').length}\n• 建议: 关注放热反应控制，确保安全措施到位`
    case 'environmental':
      return `• 环保性评分: ${scores.environmental}分\n• 平均纯度: ${completedExps.length > 0 ? Math.round(completedExps.reduce((sum, e) => sum + (e.purity || 0), 0) / completedExps.length) : 0}%\n• 建议: 优化溶剂回收，减少废物排放`
    case 'cost':
      return `• 成本评分: ${scores.cost}分\n• 平均收率: ${avgYield}%\n• 建议: 收率越高成本越低，建议优化关键步骤`
    case 'feasibility': {
      const successRate = experiments.length > 0 ? Math.round(completedExps.length / experiments.length * 100) : 0
      return `• 可行性评分: ${scores.feasibility}分\n• 实验成功率: ${successRate}%\n• 完成实验数: ${completedExps.length}/${experiments.length}\n• 建议: 成功率较高，放大可行性好`
    }
    default:
      return ''
  }
}

function generateSafetyNote(experiments: ExperimentRecord[], score: number): string {
  const failedCount = experiments.filter(e => e.status === 'failed').length
  return `安全性评分${score}分。实验失败${failedCount}次，${failedCount > 0 ? '需关注操作安全' : '操作安全可控'}。建议加强放热反应监控。`
}

function generateEnvironmentalNote(score: number): string {
  return `环保性评分${score}分。建议优化溶剂回收率，减少E因子。`
}

function generateCostNote(score: number, experiments: ExperimentRecord[]): string {
  const completed = experiments.filter(e => e.status === 'completed')
  const avgYield = completed.length > 0 ? Math.round(completed.reduce((sum, e) => sum + (e.yield || 0), 0) / completed.length) : 0
  return `成本评分${score}分，平均收率${avgYield}%。建议优化关键步骤提高收率以降低成本。`
}

function generateFeasibilityNote(score: number, experiments: ExperimentRecord[]): string {
  const completed = experiments.filter(e => e.status === 'completed')
  const successRate = experiments.length > 0 ? Math.round(completed.length / experiments.length * 100) : 0
  return `可行性评分${score}分，实验成功率${successRate}%。放大风险可控。`
}
