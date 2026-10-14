'use client'

import { useState, useMemo } from 'react'
import { Card, Button, Space, Tag, Table, Form, Input, InputNumber, Select, App, Tabs, Collapse, Row, Col } from 'antd'
import Alert from '@/components/shared/PlatformNotice'
import { CheckCircleOutlined, PlusOutlined, DeleteOutlined, ExperimentOutlined, BarChartOutlined, TableOutlined, SettingOutlined } from '@ant-design/icons'
import ReactECharts from '@/components/shared/ThemedEChart'
import 'echarts-gl'
import { buildMeasuredDOEOption, completeMeasuredRuns } from './measuredDOE'
import type { DOEExperiment, DOEFactor, DOEResponse, DOERun, DOEDesignType, ReactionStep } from '@/types/rd'


const DEFAULT_FACTORS: DOEFactor[] = [
    { name: '反应温度', symbol: 'A', type: 'numeric', levels: { lower: 60, upper: 80, steps: 3 }, unit: '°C' },
    { name: '反应时间', symbol: 'B', type: 'numeric', levels: { lower: 2, upper: 6, steps: 3 }, unit: 'h' },
    { name: '投料比例', symbol: 'C', type: 'numeric', levels: { lower: 1.0, upper: 1.5, steps: 3 }, unit: 'mol' },
  ]

const DEFAULT_RESPONSES: DOEResponse[] = [
    { name: '收率', unit: '%', target: 'maximize', weight: 60 },
    { name: '纯度', unit: '%', target: 'target_value', target_value: 99.0, weight: 40 },
  ]

// Helper component to replace deprecated addonBefore
function LabeledInput({ label, ...props }: { label: string } & React.ComponentProps<typeof Input>) {
  return (
    <Space.Compact style={{ width: '100%' }}>
      <div style={{ padding: '0 8px', background: '#fafafa', border: '1px solid #d9d9d9', borderRadius: '6px 0 0 6px', display: 'flex', alignItems: 'center', fontSize: 12, color: '#666', whiteSpace: 'nowrap' }}>{label}</div>
      <Input {...props} style={{ ...((props.style as any) || {}), borderRadius: '0 6px 6px 0' }} />
    </Space.Compact>
  )
}

function LabeledInputNumber({ label, ...props }: { label: string } & React.ComponentProps<typeof InputNumber>) {
  return (
    <Space.Compact style={{ width: '100%' }}>
      <div style={{ padding: '0 8px', background: '#fafafa', border: '1px solid #d9d9d9', borderRadius: '6px 0 0 6px', display: 'flex', alignItems: 'center', fontSize: 12, color: '#666', whiteSpace: 'nowrap' }}>{label}</div>
      <InputNumber {...props} style={{ ...((props.style as any) || {}), borderRadius: '0 6px 6px 0' }} />
    </Space.Compact>
  )
}

interface ModuleDOEProps {
  optimizationId: string
  initialData?: DOEExperiment
  reactionSteps?: ReactionStep[]
  currentStepId?: string
  onStepChange?: (stepId: string) => void
  onComplete: (experiment: DOEExperiment) => void
}

export function ModuleDOE({ optimizationId, initialData, reactionSteps, currentStepId, onStepChange, onComplete }: ModuleDOEProps) {
  const { message } = App.useApp()
  const [selectedStepId, setSelectedStepId] = useState(currentStepId || reactionSteps?.[0]?.id)

  // Get current step's DOE experiment
  const currentStep = reactionSteps?.find(s => s.id === selectedStepId)
  const currentDoeData = currentStep?.doe_experiment || initialData

  const [activeTab, setActiveTab] = useState(currentDoeData?.runs.some(r => r.status === 'completed') ? 'data' : 'design')

  // Handle step change
  const handleStepChange = (stepId: string) => {
    const next = reactionSteps?.find((step) => step.id === stepId)?.doe_experiment
    setSelectedStepId(stepId)
    setDesignType(next?.design_type || 'orthogonal')
    setFactors(next?.factors || DEFAULT_FACTORS)
    setResponses(next?.responses || DEFAULT_RESPONSES)
    setRuns(next?.runs || [])
    setMatrixGenerated(Boolean(next?.runs.length))
    setSelectedResponse(next?.responses[0]?.name || '')
    setConclusion(next?.conclusion || '')
    setActiveTab(next?.runs.length ? 'data' : 'design')
    onStepChange?.(stepId)
  }

  // DOE 设计状态
  const [designType, setDesignType] = useState<DOEDesignType>(currentDoeData?.design_type || 'orthogonal')
  const [factors, setFactors] = useState<DOEFactor[]>(currentDoeData?.factors || DEFAULT_FACTORS)
  const [responses, setResponses] = useState<DOEResponse[]>(currentDoeData?.responses || DEFAULT_RESPONSES)

  // 实验矩阵
  const [runs, setRuns] = useState<DOERun[]>(currentDoeData?.runs || [])
  const [matrixGenerated, setMatrixGenerated] = useState(currentDoeData?.runs?.length ? true : false)
  const [trialScheme, setTrialScheme] = useState<string>('auto')
  const [customRuns, setCustomRuns] = useState<number>(12)

  // 实测图表与人工记录
  const [selectedResponse, setSelectedResponse] = useState(currentDoeData?.responses[0]?.name || '')
  const completedRuns = useMemo(() => completeMeasuredRuns(factors, responses, runs), [factors, responses, runs])
  const [conclusion, setConclusion] = useState(currentDoeData?.conclusion || '')

  // 生成实验矩阵
  const handleGenerateMatrix = () => {
    if (factors.length === 0) {
      message.warning('请至少添加一个因素')
      return
    }
    if (responses.length === 0) {
      message.warning('请至少添加一个响应变量')
      return
    }

    // 根据试验方案调整因素数
    let activeFactors = factors
    if (trialScheme === 'L9') activeFactors = factors.slice(0, 3)
    else if (trialScheme === 'L16') activeFactors = factors.slice(0, 4)
    else if (trialScheme === 'L25') activeFactors = factors.slice(0, 5)
    else activeFactors = factors.slice(0, 4) // 最多4个因素
    const generatedRuns: DOERun[] = []

    // 计算每个因素的水平值
    const getFactorLevels = (factor: DOEFactor): (string | number)[] => {
      if (factor.type === 'categorical') {
        return factor.levels as string[]
      }
      const bounds = factor.levels as { lower: number; upper: number; steps?: number }
      const steps = bounds.steps || 3
      const stepSize = (bounds.upper - bounds.lower) / (steps - 1)
      return Array.from({ length: steps }, (_, i) => Math.round((bounds.lower + i * stepSize) * 100) / 100)
    }

    if (designType === 'orthogonal') {
      // 正交设计 - 根据试验方案选择
      const levelsPerFactor = activeFactors.map(f => getFactorLevels(f))
      const maxLevels = Math.max(...levelsPerFactor.map(l => l.length))
      let runs_count: number
      if (trialScheme === 'L9') runs_count = 9
      else if (trialScheme === 'L16') runs_count = 16
      else if (trialScheme === 'L25') runs_count = 25
      else if (trialScheme === 'custom') runs_count = customRuns
      else {
        runs_count = Math.pow(maxLevels, Math.min(activeFactors.length, 3))
      }
      
      for (let i = 0; i < runs_count; i++) {
        const factorValues: Record<string, string | number> = {}
        activeFactors.forEach((factor, idx) => {
          const levels = levelsPerFactor[idx]
          const levelIdx = Math.floor(i / Math.pow(maxLevels, idx)) % levels.length
          factorValues[factor.symbol] = levels[levelIdx]
        })
        generatedRuns.push({
          run_no: i + 1,
          factor_values: factorValues,
          response_values: {},
          status: 'planned',
        })
      }
    } else if (designType === 'response_surface') {
      // 响应面设计 - 根据试验方案选择
      const numericOnly = activeFactors.filter(f => f.type === 'numeric')
      const categoricalOnly = activeFactors.filter(f => f.type === 'categorical')
      let centerRuns = 3
      if (trialScheme === 'CCD') centerRuns = 3
      else if (trialScheme === 'BBD') centerRuns = 3
      else if (trialScheme === 'custom') {
        // 自定义试验数目时，调整中心点数量以达到目标总数
        const factorialRuns = Math.pow(2, Math.min(numericOnly.length, 3))
        const axialRuns = 2 * Math.min(numericOnly.length, 3)
        centerRuns = Math.max(1, customRuns - factorialRuns - axialRuns)
      }
      const factorialRuns = Math.pow(2, Math.min(numericOnly.length, 3))
      const axialRuns = 2 * Math.min(numericOnly.length, 3)
      const totalRuns = factorialRuns + axialRuns + centerRuns

      for (let i = 0; i < totalRuns; i++) {
        const factorValues: Record<string, string | number> = {}
        // 分类因素固定取第一个水平
        categoricalOnly.forEach(factor => {
          const levels = factor.levels as string[]
          factorValues[factor.symbol] = levels[0]
        })
        // 数值因素按CCD设计
        numericOnly.forEach((factor, idx) => {
          const bounds = factor.levels as { lower: number; upper: number }
          const center = (bounds.lower + bounds.upper) / 2
          const range = (bounds.upper - bounds.lower) / 2

          if (i < factorialRuns) {
            const level = (Math.floor(i / Math.pow(2, idx)) % 2) === 0 ? -1 : 1
            factorValues[factor.symbol] = Math.round((center + level * range) * 100) / 100
          } else if (i < factorialRuns + axialRuns) {
            const axialIdx = i - factorialRuns
            const factorIdx = Math.floor(axialIdx / 2)
            const direction = axialIdx % 2 === 0 ? -1.414 : 1.414
            if (idx === factorIdx) {
              factorValues[factor.symbol] = Math.round((center + direction * range) * 100) / 100
            } else {
              factorValues[factor.symbol] = Math.round(center * 100) / 100
            }
          } else {
            factorValues[factor.symbol] = Math.round(center * 100) / 100
          }
        })
        generatedRuns.push({
          run_no: i + 1,
          factor_values: factorValues,
          response_values: {},
          status: 'planned',
        })
      }
    } else {
      // Plackett-Burman 或 Custom - 2水平设计
      const numericOnly = activeFactors.filter(f => f.type === 'numeric')
      const categoricalOnly = activeFactors.filter(f => f.type === 'categorical')
      const runs_count = Math.pow(2, Math.min(numericOnly.length, 4))
      
      for (let i = 0; i < runs_count; i++) {
        const factorValues: Record<string, string | number> = {}
        // 分类因素固定取第一个水平
        categoricalOnly.forEach(factor => {
          const levels = factor.levels as string[]
          factorValues[factor.symbol] = levels[0]
        })
        // 数值因素按2水平设计
        numericOnly.forEach((factor, idx) => {
          const bounds = factor.levels as { lower: number; upper: number }
          const level = (Math.floor(i / Math.pow(2, idx)) % 2) === 0 ? bounds.lower : bounds.upper
          factorValues[factor.symbol] = Math.round(level * 100) / 100
        })
        generatedRuns.push({
          run_no: i + 1,
          factor_values: factorValues,
          response_values: {},
          status: 'planned',
        })
      }
    }

    setRuns(generatedRuns)
    setMatrixGenerated(true)
    setActiveTab('data')
    message.success(`实验矩阵已生成：${generatedRuns.length} 组实验`)
  }

  // 更新实验结果
  const handleUpdateRun = (runNo: number, field: string, value: number | null) => {
    setRuns(prev => prev.map(r => {
      if (r.run_no === runNo) {
        const responseValues = { ...r.response_values }
        if (value === null) delete responseValues[field]
        else responseValues[field] = value
        const updated: DOERun = { ...r, response_values: responseValues, status: 'completed' }
        return { ...updated, status: completeMeasuredRuns(factors, responses, [updated]).length ? 'completed' as const : 'planned' as const }
      }
      return r
    }))
  }

  // Statistical fitting is not connected; only recorded measurements can be confirmed.
  const handleConfirm = () => {
    if (!completedRuns.length) {
      message.warning('请至少完整录入一组实验的因素和全部响应值')
      return
    }
    onComplete({
      id: currentDoeData?.id || `doe-${optimizationId}`, design_type: designType,
      factors, responses, runs, conclusion,
    })
  }

  // 因素管理
  const addFactor = () => {
    const symbols = 'ABCDEFGH'
    const newSymbol = symbols[factors.length] || `X${factors.length + 1}`
    setFactors([...factors, {
      name: `因素${factors.length + 1}`,
      symbol: newSymbol,
      type: 'numeric',
      levels: { lower: 0, upper: 100, steps: 3 },
      unit: '',
    }])
  }

  const updateFactor = (index: number, updates: Partial<DOEFactor>) => {
    setFactors(prev => prev.map((f, i) => i === index ? { ...f, ...updates } : f))
  }

  const removeFactor = (index: number) => {
    setFactors(prev => prev.filter((_, i) => i !== index))
  }

  // 响应变量管理
  const addResponse = () => {
    setResponses([...responses, { name: `响应${responses.length + 1}`, unit: '', target: 'maximize', weight: 50 }])
  }

  const updateResponse = (index: number, updates: Partial<DOEResponse>) => {
    setResponses(prev => prev.map((r, i) => i === index ? { ...r, ...updates } : r))
  }

  const removeResponse = (index: number) => {
    setResponses(prev => prev.filter((_, i) => i !== index))
  }

  // 实验矩阵表格列
  const runColumns = [
    { title: '实验号', dataIndex: 'run_no', key: 'run_no', width: 70 },
    ...factors.map(f => ({
      title: `${f.name}(${f.symbol})${f.unit ? ` [${f.unit}]` : ''}`,
      key: f.symbol,
      width: 120,
      render: (_: unknown, record: DOERun) => {
        const val = record.factor_values[f.symbol]
        return typeof val === 'number' ? val.toFixed(1) : val
      },
    })),
    ...responses.map(r => ({
      title: `${r.name} [${r.unit}]`,
      key: `resp_${r.name}`,
      width: 130,
      render: (_: unknown, record: DOERun) => (
        <InputNumber
          size="small"
          style={{ width: 100 }}
          value={record.response_values[r.name]}
          onChange={(val) => handleUpdateRun(record.run_no, r.name, val)}
          placeholder="结果"
        />
      ),
    })),
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 80,
      render: (s: string) => <Tag color={s === 'completed' ? 'green' : s === 'failed' ? 'red' : 'default'}>{s === 'completed' ? '完成' : s === 'failed' ? '失败' : '待做'}</Tag>,
    },
  ]

  const responseSurfaceOption = useMemo(() => buildMeasuredDOEOption(factors, responses, runs, selectedResponse),
    [factors, responses, runs, selectedResponse])

  return (
    <div>
      {reactionSteps && reactionSteps.length > 0 && (
        <Card style={{ marginBottom: 16 }}>
          <div style={{ marginBottom: 12, fontWeight: 500 }}>反应步骤选择：</div>
          <Select
            aria-label="反应步骤"
            value={selectedStepId}
            onChange={handleStepChange}
            style={{ width: '100%' }}
            options={reactionSteps.map(step => ({
              value: step.id,
              label: `${step.step_order}. ${step.step_name} ${step.status === 'completed' ? '✓' : step.status === 'in_progress' ? '⏳' : '○'}`
            }))}
          />
          {currentStep?.description && (
            <div style={{ marginTop: 8, color: '#666', fontSize: '13px' }}>
              {currentStep.description}
            </div>
          )}
        </Card>
      )}

      <Card>
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={[
            {
              key: 'design',
              label: <span><SettingOutlined /> 1a. DOE方案设计</span>,
              children: (
                <div>
                  <Alert
                    title="DOE实验设计"
                    description="选择实验设计类型，定义因素和水平，生成实验矩阵。DOE方法可以高效地探索多因素影响，找到最优工艺参数组合。"
                    type="info"
                    showIcon
                    style={{ marginBottom: 16 }}
                  />

                  <div style={{ marginBottom: 16 }}>
                    <div style={{ fontWeight: 500, marginBottom: 8 }}>设计类型</div>
                    <Select
                      style={{ width: 300 }}
                      value={designType}
                      onChange={setDesignType}
                      options={[
                        { value: 'orthogonal', label: '正交设计（L9/L16/L25）' },
                        { value: 'response_surface', label: '响应面设计（CCD/BBD）' },
                        { value: 'plackett_burman', label: 'Plackett-Burman 筛选设计' },
                        { value: 'custom', label: '自定义设计' },
                      ]}
                    />

                  </div>
                  <div style={{ marginBottom: 16, marginTop: 16 }}>
                    <div style={{ fontWeight: 500, marginBottom: 8 }}>试验方案</div>
                    <Select
                      style={{ width: 300 }}
                      value={trialScheme}
                      onChange={setTrialScheme}
                      options={
                        designType === 'orthogonal' ? [
                          { value: 'auto', label: '自动（根据因素数计算）' },
                          { value: 'L9', label: 'L9 (3水平, 最多3因素, 9次试验)' },
                          { value: 'L16', label: 'L16 (4水平, 最多4因素, 16次试验)' },
                          { value: 'L25', label: 'L25 (5水平, 最多5因素, 25次试验)' },
                          { value: 'custom', label: '自定义试验数目' },
                        ] : designType === 'response_surface' ? [
                          { value: 'auto', label: '自动（CCD中心复合设计）' },
                          { value: 'CCD', label: 'CCD (中心复合设计, 推荐)' },
                          { value: 'BBD', label: 'BBD (Box-Behnken设计)' },
                          { value: 'custom', label: '自定义试验数目' },
                        ] : [
                          { value: 'auto', label: '自动（根据因素数计算）' },
                          { value: 'custom', label: '自定义试验数目' },
                        ]
                      }
                    />
                  </div>

                  {trialScheme === 'custom' && (
                    <div style={{ marginBottom: 16 }}>
                      <div style={{ fontWeight: 500, marginBottom: 8 }}>试验数目</div>
                      <Space.Compact style={{ width: 300 }}>
                        <InputNumber
                          style={{ width: 'calc(100% - 40px)' }}
                          value={customRuns}
                          onChange={(v) => setCustomRuns(v ?? 12)}
                          min={4}
                          max={100}
                          step={1}
                        />
                        <div style={{ padding: '0 12px', background: '#fafafa', border: '1px solid #d9d9d9', borderRadius: '0 6px 6px 0', display: 'flex', alignItems: 'center', fontSize: 14, color: '#666' }}>次</div>
                      </Space.Compact>
                      <div style={{ fontSize: 12, color: '#999', marginTop: 4 }}>
                        建议：3因素9-27次，4因素16-32次
                      </div>
                    </div>
                  )}

                  {/* 因素设置 */}
                  <div style={{ marginBottom: 16 }}>
                    <div style={{ fontWeight: 500, marginBottom: 8 }}>
                      <ExperimentOutlined /> 因素设置
                      <Button type="link" icon={<PlusOutlined />} onClick={addFactor} size="small">添加因素</Button>
                    </div>
                    <div style={{ fontSize: 12, color: '#666', marginBottom: 8, padding: '4px 8px', background: '#f0f0f0', borderRadius: 4 }}>
                      调试：{factors.map((f, i) => `${f.name}(${f.symbol}): ${JSON.stringify(f.levels)}`).join(' | ')}
                    </div>
                    {factors.map((factor, idx) => (
                      <Card key={idx} size="small" style={{ marginBottom: 8, backgroundColor: '#fafafa' }}>
                        <Row gutter={16} align="middle">
                          <Col span={4}>
                            <LabeledInput label="名称"
                              value={factor.name}
                              onChange={(e) => updateFactor(idx, { name: e.target.value })}
                            />
                          </Col>
                          <Col span={2}>
                            <LabeledInput label="符号"
                              value={factor.symbol}
                              onChange={(e) => updateFactor(idx, { symbol: e.target.value })}
                              style={{ width: 70 }}
                            />
                          </Col>
                          <Col span={3}>
                            <LabeledInput label="单位"
                              value={factor.unit}
                              onChange={(e) => updateFactor(idx, { unit: e.target.value })}
                            />
                          </Col>
                          <Col span={4}>
                            <LabeledInputNumber label="下限"
                              value={(factor.levels as { lower: number }).lower}
                              onChange={(v) => updateFactor(idx, { levels: { ...(factor.levels as object), lower: v ?? 0 } as DOEFactor['levels'] })}
                              style={{ width: '100%' }}
                            />
                          </Col>
                          <Col span={4}>
                            <LabeledInputNumber label="上限"
                              value={(factor.levels as { upper: number }).upper}
                              onChange={(v) => updateFactor(idx, { levels: { ...(factor.levels as object), upper: v ?? 0 } as DOEFactor['levels'] })}
                              style={{ width: '100%' }}
                            />
                          </Col>
                          <Col span={3}>
                            <LabeledInputNumber label="水平数"
                              value={(factor.levels as { steps?: number }).steps || 3}
                              min={2}
                              max={5}
                              onChange={(v) => updateFactor(idx, { levels: { ...(factor.levels as object), steps: v ?? 3 } as DOEFactor['levels'] })}
                              style={{ width: '100%' }}
                            />
                          </Col>
                          <Col span={2}>
                            <Button danger icon={<DeleteOutlined />} onClick={() => removeFactor(idx)} />
                          </Col>
                        </Row>
                      </Card>
                    ))}
                  </div>

                  {/* 响应变量设置 */}
                  <div style={{ marginBottom: 16 }}>
                    <div style={{ fontWeight: 500, marginBottom: 8 }}>
                      <BarChartOutlined /> 响应变量
                      <Button type="link" icon={<PlusOutlined />} onClick={addResponse} size="small">添加响应</Button>
                    </div>
                    {responses.map((resp, idx) => (
                      <Card key={idx} size="small" style={{ marginBottom: 8, backgroundColor: '#fafafa' }}>
                        <Row gutter={16} align="middle">
                          <Col span={5}>
                            <LabeledInput label="名称"
                              value={resp.name}
                              onChange={(e) => updateResponse(idx, { name: e.target.value })}
                            />
                          </Col>
                          <Col span={3}>
                            <LabeledInput label="单位"
                              value={resp.unit}
                              onChange={(e) => updateResponse(idx, { unit: e.target.value })}
                            />
                          </Col>
                          <Col span={5}>
                            <Select
                              style={{ width: '100%' }}
                              value={resp.target}
                              onChange={(v) => updateResponse(idx, { target: v })}
                              options={[
                                { value: 'maximize', label: '最大化' },
                                { value: 'minimize', label: '最小化' },
                                { value: 'target_value', label: '目标值' },
                              ]}
                            />
                          </Col>
                          {resp.target === 'target_value' && (
                            <Col span={4}>
                              <LabeledInputNumber label="目标"
                                value={resp.target_value}
                                onChange={(v) => updateResponse(idx, { target_value: (v as number) || undefined })}
                                style={{ width: '100%' }}
                              />
                            </Col>
                          )}
                          <Col span={4}>
                            <LabeledInputNumber label="权重%"
                              value={resp.weight}
                              min={0}
                              max={100}
                              onChange={(v) => updateResponse(idx, { weight: (v as number) || 0 })}
                              style={{ width: '100%' }}
                            />
                          </Col>
                          <Col span={2}>
                            <Button danger icon={<DeleteOutlined />} onClick={() => removeResponse(idx)} />
                          </Col>
                        </Row>
                      </Card>
                    ))}
                    <div style={{ fontSize: 12, color: '#999' }}>
                      权重合计：{responses.reduce((s, r) => s + r.weight, 0)}%
                      {responses.reduce((s, r) => s + r.weight, 0) !== 100 && <Tag color="warning">建议调整为100%</Tag>}
                    </div>
                  </div>

                  <Button
                    type="primary"
                    icon={<ExperimentOutlined />}
                    onClick={handleGenerateMatrix}
                    size="large"
                  >
                    🧪 生成实验矩阵
                  </Button>
                </div>
              ),
            },
            {
              key: 'data',
              label: <span><TableOutlined /> 1b. 实验数据录入</span>,
              children: (
                <div>
                  {!matrixGenerated ? (
                    <Alert title="请先在【DOE方案设计】中生成实验矩阵" type="warning" showIcon />
                  ) : (
                    <>
                      <Alert
                        title={`共 ${runs.length} 组实验，已完成 ${runs.filter(r => r.status === 'completed').length} 组`}
                        description="请按实验矩阵完成实验后，在对应行录入实验结果"
                        type="info"
                        showIcon
                        style={{ marginBottom: 16 }}
                      />
                      <Table
                        columns={runColumns}
                        dataSource={runs}
                        rowKey="run_no"
                        pagination={false}
                        size="small"
                        scroll={{ x: 800 }}
                      />
                      <div style={{ marginTop: 16 }}>
                        <Space>
                          <Button
                            type="primary"
                            icon={<BarChartOutlined />}
                            onClick={() => setActiveTab('analysis')}
                            disabled={!completedRuns.length}
                          >
                            📊 查看实测图表
                          </Button>
                          <Tag>已完成 {runs.filter(r => r.status === 'completed').length}/{runs.length} 组</Tag>
                        </Space>
                      </div>
                    </>
                  )}
                </div>
              ),
            },
            {
              key: 'analysis',
              label: <span><BarChartOutlined /> 1c. 实测数据与图表</span>,
              children: (
                <div>
                  <Alert type="info" title="统计拟合尚未接入，当前仅展示实测实验数据"
                    description="图表直接读取已录入的实验点，不生成 ANOVA、R²、预测响应、最优条件或 CPP 判断。历史拟合结果不作为本图数据或确认依据。" showIcon />
                  <Space style={{ marginBlock: 16 }} wrap>
                    <span>响应指标：</span>
                    <Select aria-label="实测响应指标" style={{ minWidth: 160 }}
                      value={responses.some((response) => response.name === selectedResponse) ? selectedResponse : responses[0]?.name}
                      options={responses.map((response) => ({ value: response.name, label: response.name }))}
                      onChange={setSelectedResponse} />
                    <Tag>完整录入 {completedRuns.length}/{runs.length} 组</Tag>
                  </Space>
                  {responseSurfaceOption ? <Card size="small" title="3D 实测实验点" style={{ marginBottom: 16 }}>
                    <ReactECharts option={responseSurfaceOption} style={{ height: 400 }} notMerge />
                  </Card> : <Alert type="warning" title="暂无可绘制的实测实验点"
                    description="三维图需要至少两个数值因素，以及已录入的有限响应值；缺失值、失败或未完成实验不会生成数据点。" showIcon />}
                  <Table columns={runColumns} dataSource={runs.filter((run) => run.status === 'completed')}
                    rowKey="run_no" pagination={false} size="small" scroll={{ x: 800 }} />
                  <div style={{ marginTop: 16 }}>
                    <div style={{ marginBottom: 8 }}>实验记录与人工结论</div>
                    <Input.TextArea rows={4} value={conclusion} onChange={(event) => setConclusion(event.target.value)}
                      placeholder="记录实测现象和人工判断；统计拟合尚未接入" />
                  </div>
                </div>
              ),
            },
          ]}
        />
      </Card>

      <Card>
        <Space>
          <Button
            type="primary"
            icon={<CheckCircleOutlined />}
            onClick={handleConfirm}
            size="large"
            disabled={!completedRuns.length}
          >
            ✓ 确认实测记录并进入下一步（杂质研究）
          </Button>
          {!completedRuns.length && (
            <Tag>请先完整录入至少一组实验</Tag>
          )}
        </Space>
      </Card>
    </div>
  )
}
