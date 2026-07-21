'use client'

import { useState, useMemo } from 'react'
import { Card, Button, Space, Tag, Table, Form, Input, InputNumber, Select, App, Tabs, Alert, Collapse, Row, Col, Statistic, Descriptions } from 'antd'
import { CheckCircleOutlined, PlusOutlined, DeleteOutlined, ExperimentOutlined, BarChartOutlined, TableOutlined, SettingOutlined } from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import 'echarts-gl'
import type { DOEExperiment, DOEFactor, DOEResponse, DOERun, DOEDesignType, DOEAnalysisResult, ReactionStep } from '@/types/rd'


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
    setSelectedStepId(stepId)
    onStepChange?.(stepId)
  }

  // DOE 设计状态
  const [designType, setDesignType] = useState<DOEDesignType>(currentDoeData?.design_type || 'orthogonal')
  const [factors, setFactors] = useState<DOEFactor[]>(currentDoeData?.factors || [
    { name: '反应温度', symbol: 'A', type: 'numeric', levels: { lower: 60, upper: 80, steps: 3 }, unit: '°C' },
    { name: '反应时间', symbol: 'B', type: 'numeric', levels: { lower: 2, upper: 6, steps: 3 }, unit: 'h' },
    { name: '投料比例', symbol: 'C', type: 'numeric', levels: { lower: 1.0, upper: 1.5, steps: 3 }, unit: 'mol' },
  ])
  const [responses, setResponses] = useState<DOEResponse[]>(currentDoeData?.responses || [
    { name: '收率', unit: '%', target: 'maximize', weight: 60 },
    { name: '纯度', unit: '%', target: 'target_value', target_value: 99.0, weight: 40 },
  ])

  // 实验矩阵
  const [runs, setRuns] = useState<DOERun[]>(currentDoeData?.runs || [])
  const [matrixGenerated, setMatrixGenerated] = useState(currentDoeData?.runs?.length ? true : false)
  const [trialScheme, setTrialScheme] = useState<string>('auto')
  const [customRuns, setCustomRuns] = useState<number>(12)

  // 分析结果
  const [analysisResult, setAnalysisResult] = useState<DOEAnalysisResult | undefined>(currentDoeData?.analysis_result)
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
    let generatedRuns: DOERun[] = []

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
  const handleUpdateRun = (runNo: number, field: string, value: number) => {
    setRuns(prev => prev.map(r => {
      if (r.run_no === runNo) {
        return {
          ...r,
          response_values: { ...r.response_values, [field]: value },
          status: 'completed' as const,
        }
      }
      return r
    }))
  }

  // 执行统计分析（模拟）
  const handleAnalyze = () => {
    const completedRuns = runs.filter(r => r.status === 'completed')
    if (completedRuns.length < 4) {
      message.warning('至少需要完成4组实验才能进行统计分析')
      return
    }

    // 模拟 ANOVA 分析结果
    const anovaTable = [
      { source: '模型', df: factors.length, sum_of_squares: 245.6, mean_square: 81.87, f_value: 12.34, p_value: 0.001, significance: '**' },
      ...factors.map((f, i) => ({
        source: f.name,
        df: 1,
        sum_of_squares: 50 + Math.random() * 100,
        mean_square: 50 + Math.random() * 100,
        f_value: 5 + Math.random() * 20,
        p_value: Math.random() * 0.05,
        significance: Math.random() > 0.3 ? '*' : 'ns',
      })),
      { source: '残差', df: completedRuns.length - factors.length - 1, sum_of_squares: 33.2, mean_square: 6.64, f_value: 0, p_value: 0, significance: '' },
      { source: '总计', df: completedRuns.length - 1, sum_of_squares: 278.8, mean_square: 0, f_value: 0, p_value: 0, significance: '' },
    ]

    // 找最优条件
    const bestRun = completedRuns.reduce((best, run) => {
      const bestScore = responses.reduce((s, r) => s + (best.response_values[r.name] || 0) * r.weight / 100, 0)
      const runScore = responses.reduce((s, r) => s + (run.response_values[r.name] || 0) * r.weight / 100, 0)
      return runScore > bestScore ? run : best
    })

    const optimalConditions = { ...bestRun.factor_values } as Record<string, number>
    const predictedResponse: Record<string, number> = {}
    responses.forEach(r => {
      predictedResponse[r.name] = Math.round((bestRun.response_values[r.name] || 0) * 1.05 * 100) / 100
    })

    const significantFactors = factors.filter((_, i) => anovaTable[i + 1]?.p_value < 0.05).map(f => f.name)

    const result: DOEAnalysisResult = {
      anova_table: anovaTable,
      regression_model: `Y = ${Math.round(Math.random() * 10 + 70)} + ${factors.map((f, i) => `${(Math.random() * 5 + 1).toFixed(2)}×${f.symbol}`).join(' + ')}`,
      r_squared: Math.round((0.85 + Math.random() * 0.1) * 1000) / 1000,
      adjusted_r_squared: Math.round((0.80 + Math.random() * 0.1) * 1000) / 1000,
      optimal_conditions: optimalConditions,
      predicted_response: predictedResponse,
      significant_factors: significantFactors,
    }

    setAnalysisResult(result)
    setActiveTab('analysis')
    message.success('统计分析完成！')
  }

  // 确认完成
  const handleConfirm = () => {
    if (!analysisResult) {
      message.warning('请先完成统计分析')
      return
    }
    const experiment: DOEExperiment = {
      id: `doe-${optimizationId}`,
      design_type: designType,
      factors,
      responses,
      runs,
      analysis_result: analysisResult,
      conclusion: conclusion || `DOE优化完成，最优条件：${Object.entries(analysisResult.optimal_conditions).map(([k, v]) => `${k}=${v}`).join(', ')}，R²=${analysisResult.r_squared}`,
    }
    onComplete(experiment)
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

  // ANOVA 表格列
  const anovaColumns = [
    { title: '变异来源', dataIndex: 'source', key: 'source', width: 120 },
    { title: '自由度', dataIndex: 'df', key: 'df', width: 80 },
    { title: '平方和', dataIndex: 'sum_of_squares', key: 'sum_of_squares', width: 100, render: (v: number) => v.toFixed(2) },
    { title: '均方', dataIndex: 'mean_square', key: 'mean_square', width: 100, render: (v: number) => v.toFixed(2) },
    { title: 'F值', dataIndex: 'f_value', key: 'f_value', width: 80, render: (v: number) => v.toFixed(2) },
    { title: 'P值', dataIndex: 'p_value', key: 'p_value', width: 80, render: (v: number) => v < 0.001 ? '<0.001' : v.toFixed(3) },
    { title: '显著性', dataIndex: 'significance', key: 'significance', width: 80, render: (v: string) => <Tag color={v === '**' ? 'red' : v === '*' ? 'orange' : 'default'}>{v || '-'}</Tag> },
  ]

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
          onChange={(val) => val != null && handleUpdateRun(record.run_no, r.name, val)}
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

  // 响应面图
  const responseSurfaceOption = useMemo(() => {
    if (!analysisResult || factors.length < 2) return null
    const f1 = factors[0]
    const f2 = factors[1]
    const bounds1 = f1.levels as { lower: number; upper: number }
    const bounds2 = f2.levels as { lower: number; upper: number }

    const xData = Array.from({ length: 10 }, (_, i) => bounds1.lower + (bounds1.upper - bounds1.lower) * i / 9)
    const yData = Array.from({ length: 10 }, (_, i) => bounds2.lower + (bounds2.upper - bounds2.lower) * i / 9)

    const surfaceData: number[][][] = []
    for (let i = 0; i < xData.length; i++) {
      const row: number[][] = []
      for (let j = 0; j < yData.length; j++) {
        const val = 70 + 15 * Math.sin(i / 3) * Math.cos(j / 3) + Math.random() * 5
        row.push([xData[i], yData[j], Math.round(val * 10) / 10])
      }
      surfaceData.push(row)
    }

    return {
      tooltip: {},
      xAxis3D: { type: 'value', name: `${f1.name}(${f1.unit})` },
      yAxis3D: { type: 'value', name: `${f2.name}(${f2.unit})` },
      zAxis3D: { type: 'value', name: `${responses[0]?.name || '响应'}(${responses[0]?.unit || ''})` },
      grid3D: { viewControl: { projection: 'perspective' } },
      series: [{
        type: 'surface',
        data: surfaceData.flat(),
        shading: 'color',
        itemStyle: { opacity: 0.8 },
      }],
    }
  }, [analysisResult, factors, responses])

  return (
    <div>
      {reactionSteps && reactionSteps.length > 0 && (
        <Card style={{ marginBottom: 16 }}>
          <div style={{ marginBottom: 12, fontWeight: 500 }}>反应步骤选择：</div>
          <Select
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
                            onClick={handleAnalyze}
                            disabled={runs.filter(r => r.status === 'completed').length < 4}
                          >
                            📊 执行统计分析
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
              label: <span><BarChartOutlined /> 1c. 统计分析与优化</span>,
              children: (
                <div>
                  {!analysisResult ? (
                    <Alert title="请先完成实验数据录入并执行统计分析" type="warning" showIcon />
                  ) : (
                    <>
                      {/* 模型概览 */}
                      <Row gutter={16} style={{ marginBottom: 16 }}>
                        <Col span={6}>
                          <Card size="small"><Statistic title="R²" value={analysisResult.r_squared} precision={3} /></Card>
                        </Col>
                        <Col span={6}>
                          <Card size="small"><Statistic title="调整R²" value={analysisResult.adjusted_r_squared} precision={3} /></Card>
                        </Col>
                        <Col span={6}>
                          <Card size="small"><Statistic title="显著因素" value={analysisResult.significant_factors.length} suffix={`/ ${factors.length}`} /></Card>
                        </Col>
                        <Col span={6}>
                          <Card size="small"><Statistic title="实验完成" value={runs.filter(r => r.status === 'completed').length} suffix={`/ ${runs.length}`} /></Card>
                        </Col>
                      </Row>

                      {/* 回归模型 */}
                      <Card size="small" title="回归模型" style={{ marginBottom: 16 }}>
                        <code style={{ fontSize: 14 }}>{analysisResult.regression_model}</code>
                      </Card>

                      {/* ANOVA 表 */}
                      <Card size="small" title="方差分析表（ANOVA）" style={{ marginBottom: 16 }}>
                        <Table
                          columns={anovaColumns}
                          dataSource={analysisResult.anova_table}
                          rowKey="source"
                          pagination={false}
                          size="small"
                        />
                      </Card>

                      {/* 最优条件 */}
                      <Card size="small" title="🎯 最优工艺参数" style={{ marginBottom: 16, background: '#f6ffed' }}>
                        <Descriptions column={3}>
                          {Object.entries(analysisResult.optimal_conditions).map(([symbol, value]) => {
                            const factor = factors.find(f => f.symbol === symbol)
                            return (
                              <Descriptions.Item key={symbol} label={`${factor?.name || symbol}(${symbol})`}>
                                <Tag color="blue">{value} {factor?.unit || ''}</Tag>
                              </Descriptions.Item>
                            )
                          })}
                        </Descriptions>
                        <div style={{ marginTop: 8 }}>
                          <strong>预测响应值：</strong>
                          {Object.entries(analysisResult.predicted_response).map(([name, value]) => (
                            <Tag key={name} color="green" style={{ marginLeft: 8 }}>{name}: {value}</Tag>
                          ))}
                        </div>
                      </Card>

                      {/* 3D响应面图 */}
                      {responseSurfaceOption && (
                        <Card size="small" title="3D响应面图" style={{ marginBottom: 16 }}>
                          <ReactECharts option={responseSurfaceOption} style={{ height: 400 }} />
                        </Card>
                      )}

                      {/* 结论 */}
                      <div style={{ marginBottom: 16 }}>
                        <div style={{ fontWeight: 500, marginBottom: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <span>优化结论</span>
                          <Button
                            size="small"
                            type="primary"
                            ghost
                            onClick={() => {
                              if (!analysisResult) return
                              const factorsStr = factors.map(f => {
                                const opt = analysisResult.optimal_conditions[f.symbol]
                                return opt != null ? `${f.name}(${f.symbol})=${opt}${f.unit || ''}` : null
                              }).filter(Boolean).join('、')
                              
                              const sigFactors = analysisResult.significant_factors.length > 0
                                ? analysisResult.significant_factors.join('、')
                                : '无显著因素'
                              
                              const designName = designType === 'orthogonal' ? '正交设计' : '响应面法'
                              const targetDesc = responses[0]?.target === 'maximize' ? '最大化' : responses[0]?.target === 'minimize' ? '最小化' : '目标值'
                              const responseName = responses[0]?.name || '目标响应'
                              
                              const generatedConclusion = `基于DOE实验设计（${designName}），对${factors.length}个因素进行了优化研究。\n\n统计分析结果显示：\n• 模型拟合度：R²=${analysisResult.r_squared.toFixed(3)}，调整R²=${analysisResult.adjusted_r_squared.toFixed(3)}\n• 显著因素：${sigFactors}\n\n最优工艺条件为：${factorsStr}\n\n在此条件下，预期${responseName}可达到${targetDesc}。\n\n该优化结果具有良好的统计学意义和实际可操作性，建议作为后续工艺开发和放大的基础参数。`
                              
                              setConclusion(generatedConclusion)
                              message.success('AI结论已生成，可根据实际情况调整')
                            }}
                          >
                            🤖 AI生成结论
                          </Button>
                        </div>
                        <Input.TextArea
                          rows={6}
                          value={conclusion}
                          onChange={(e) => setConclusion(e.target.value)}
                          placeholder="输入DOE优化结论，或点击上方的AI生成按钮自动生成..."
                        />
                      </div>

                      {/* CPP评估 */}
                      <div style={{ marginBottom: 16 }}>
                        <div style={{ fontWeight: 500, marginBottom: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <span>关键工艺参数（CPP）评估</span>
                          <Button
                            size="small"
                            type="primary"
                            ghost
                            onClick={() => {
                              if (!analysisResult) return
                              
                              // Auto-generate CPP assessment from significant factors
                              const criticalParams = analysisResult.significant_factors.length > 0
                                ? analysisResult.significant_factors
                                : factors.map(f => f.symbol)
                              
                              const controlRanges: Record<string, { min: number; max: number; unit?: string; justification: string }> = {}
                              criticalParams.forEach(symbol => {
                                const factor = factors.find(f => f.symbol === symbol)
                                if (factor && factor.levels && typeof factor.levels === 'object') {
                                  const levels = factor.levels as { lower: number; upper: number }
                                  const optimal = analysisResult.optimal_conditions[symbol]
                                  if (optimal != null) {
                                    // Set control range as ±10% around optimal
                                    const range = (levels.upper - levels.lower) * 0.1
                                    controlRanges[symbol] = {
                                      min: Math.max(levels.lower, optimal - range),
                                      max: Math.min(levels.upper, optimal + range),
                                      unit: factor.unit,
                                      justification: `基于DOE优化结果，在最优值${optimal}${factor.unit || ''}基础上，考虑工艺稳健性设定控制范围。`
                                    }
                                  }
                                }
                              })
                              
                              const cppAssessment = {
                                critical_parameters: criticalParams,
                                control_ranges: controlRanges,
                                justification: `根据DOE统计分析结果，${criticalParams.join('、')}为关键工艺参数（CPP），对${responses[0]?.name || '目标响应'}有显著影响。这些参数需要在生产过程中严格控制，以确保产品质量的一致性。`,
                                assessment_date: new Date().toISOString().split('T')[0]
                              }
                              
                              // Update the analysis result with CPP assessment
                              const updatedResult = { ...analysisResult, cpp_assessment: cppAssessment }
                              setAnalysisResult(updatedResult)
                              message.success('CPP评估已生成')
                            }}
                          >
                            🤖 AI生成CPP评估
                          </Button>
                        </div>
                        
                        {analysisResult?.cpp_assessment ? (
                          <Card size="small">
                            <div style={{ marginBottom: 12 }}>
                              <strong>关键工艺参数：</strong>
                              <div style={{ marginTop: 4 }}>
                                {analysisResult.cpp_assessment.critical_parameters.map(param => (
                                  <Tag key={param} color="blue" style={{ marginBottom: 4 }}>
                                    {factors.find(f => f.symbol === param)?.name || param} ({param})
                                  </Tag>
                                ))}
                              </div>
                            </div>
                            
                            <div style={{ marginBottom: 12 }}>
                              <strong>控制范围：</strong>
                              <div style={{ marginTop: 8 }}>
                                {Object.entries(analysisResult.cpp_assessment.control_ranges).map(([symbol, range]) => {
                                  const factor = factors.find(f => f.symbol === symbol)
                                  return (
                                    <div key={symbol} style={{ marginBottom: 8, padding: '8px', background: '#f5f5f5', borderRadius: '4px' }}>
                                      <div style={{ fontWeight: 500 }}>
                                        {factor?.name || symbol} ({symbol})：{range.min.toFixed(2)} ~ {range.max.toFixed(2)} {range.unit || ''}
                                      </div>
                                      <div style={{ fontSize: '12px', color: '#666', marginTop: 4 }}>
                                        {range.justification}
                                      </div>
                                    </div>
                                  )
                                })}
                              </div>
                            </div>
                            
                            <div>
                              <strong>评估说明：</strong>
                              <div style={{ marginTop: 4, whiteSpace: 'pre-wrap' }}>
                                {analysisResult.cpp_assessment.justification}
                              </div>
                            </div>
                          </Card>
                        ) : (
                          <div style={{ padding: '20px', textAlign: 'center', color: '#999', background: '#fafafa', borderRadius: '4px' }}>
                            点击"AI生成CPP评估"按钮，基于DOE分析结果自动生成关键工艺参数评估
                          </div>
                        )}
                      </div>
                    </>
                  )}
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
            disabled={!analysisResult}
          >
            ✓ 确认并进入下一步（杂质研究）
          </Button>
          {!analysisResult && (
            <Tag>请先完成DOE设计和统计分析</Tag>
          )}
        </Space>
      </Card>
    </div>
  )
}
