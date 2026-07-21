'use client'

import { useState } from 'react'
import { Card, Button, Space, Tag, Table, Form, Input, InputNumber, Select, App, Tabs, Alert, Row, Col, Statistic, Descriptions, Modal } from 'antd'
import { CheckCircleOutlined, PlusOutlined, DeleteOutlined, BugOutlined, SafetyOutlined, RobotOutlined } from '@ant-design/icons'
import type { ImpurityStudy, Impurity, ImpurityCategory, ICHM7Class, ICHSolventClass, ControlMethod, DOEExperiment } from '@/types/rd'
import { identifyImpurities, generateIdentificationReport } from '@/lib/impurity-identifier'
import { fetchRouteById } from '@/lib/api/rd'

interface ModuleImpurityProps {
  optimizationId: string
  sourceRouteId?: string | null
  doeExperiment?: DOEExperiment
  initialData?: ImpurityStudy
  onComplete: (study: ImpurityStudy) => void
}

const categoryMap: Record<ImpurityCategory, { color: string; label: string }> = {
  process: { color: 'blue', label: '工艺杂质' },
  degradation: { color: 'orange', label: '降解杂质' },
  residual_solvent: { color: 'purple', label: '残留溶剂' },
  elemental: { color: 'magenta', label: '元素杂质' },
  genotoxic: { color: 'red', label: '基因毒性杂质' },
}

const m7ClassMap: Record<ICHM7Class, { color: string; label: string }> = {
  class1: { color: 'red', label: 'Class 1 (高关注)' },
  class2: { color: 'orange', label: 'Class 2 (有关注)' },
  class3: { color: 'blue', label: 'Class 3 (无关注)' },
  class4: { color: 'green', label: 'Class 4 (无证据)' },
  class5: { color: 'default', label: 'Class 5 (不适用)' },
}

const riskMap: Record<string, { color: string; label: string }> = {
  low: { color: 'green', label: '低' },
  medium: { color: 'orange', label: '中' },
  high: { color: 'red', label: '高' },
}

export function ModuleImpurity({ optimizationId, sourceRouteId, doeExperiment, initialData, onComplete }: ModuleImpurityProps) {
  const { message, modal } = App.useApp()
  const [activeTab, setActiveTab] = useState('identification')
  const [impurities, setImpurities] = useState<Impurity[]>(initialData?.impurities || [
    {
      id: 'imp-1',
      name: '起始物料残留',
      category: 'process',
      source: '起始物料未完全反应',
      typical_level_pct: 0.15,
      limit_ppm: 5000,
      control_method: 'process_control',
      detection_method: 'HPLC',
      risk_level: 'low',
    },
    {
      id: 'imp-2',
      name: '脱卤副产物',
      category: 'process',
      source: '脱卤反应不完全',
      typical_level_pct: 0.08,
      limit_ppm: 3000,
      control_method: 'release_test',
      detection_method: 'HPLC',
      risk_level: 'medium',
    },
    {
      id: 'imp-3',
      name: '二氯甲烷',
      category: 'residual_solvent',
      source: '萃取溶剂残留',
      ich_solvent_class: 'class2',
      limit_ppm: 600,
      typical_level_pct: 0.01,
      control_method: 'release_test',
      detection_method: 'GC',
      risk_level: 'medium',
    },
  ])
  const [controlStrategySummary, setControlStrategySummary] = useState(initialData?.control_strategy_summary || '')
  const [studyConclusion, setStudyConclusion] = useState(initialData?.conclusion || '')
  const [showForm, setShowForm] = useState(false)
  const [autoIdentifying, setAutoIdentifying] = useState(false)
  const [form] = Form.useForm()

  const handleAddImpurity = async () => {
    try {
      const values = await form.validateFields()
      const newImpurity: Impurity = {
        id: `imp-${Date.now()}`,
        name: values.name,
        category: values.category,
        source: values.source || '',
        ich_m7_class: values.ich_m7_class,
        ich_solvent_class: values.ich_solvent_class,
        limit_ppm: values.limit_ppm,
        typical_level_pct: values.typical_level_pct,
        control_method: values.control_method || 'release_test',
        detection_method: values.detection_method,
        risk_level: values.risk_level || 'medium',
        notes: values.notes,
      }
      setImpurities([...impurities, newImpurity])
      form.resetFields()
      setShowForm(false)
      message.success('杂质已添加')
    } catch {}
  }

  const handleRemoveImpurity = (id: string) => {
    setImpurities(prev => prev.filter(i => i.id !== id))
  }

  const handleUpdateImpurity = (id: string, updates: Partial<Impurity>) => {
    setImpurities(prev => prev.map(i => i.id === id ? { ...i, ...updates } : i))
  }

  const handleAutoIdentify = async () => {
    if (!sourceRouteId && !doeExperiment) {
      message.warning('无上游数据可供分析，请手动添加杂质')
      return
    }

    setAutoIdentifying(true)
    try {
      // 获取工艺路线数据
      let route = undefined
      if (sourceRouteId) {
        try {
          route = await fetchRouteById(sourceRouteId)
        } catch (e) {
          console.warn('获取工艺路线失败', e)
        }
      }

      // 调用自动识别
      const identified = identifyImpurities({
        route,
        doeExperiment,
      })

      if (identified.length === 0) {
        message.info('未识别到潜在杂质，请手动添加')
        return
      }

      // 合并到现有列表（去重）
      const existingNames = new Set(impurities.map(i => i.name.toLowerCase()))
      const newImpurities = identified.filter(i => !existingNames.has(i.name.toLowerCase()))

      if (newImpurities.length > 0) {
        setImpurities(prev => [...prev, ...newImpurities])
        
        // 显示识别报告
        const report = generateIdentificationReport(newImpurities)
        modal.success({
          title: `✓ 自动识别完成，新增 ${newImpurities.length} 种杂质`,
          content: (
            <div style={{ whiteSpace: 'pre-wrap', fontSize: 13, maxHeight: 400, overflow: 'auto' }}>
              {report}
            </div>
          ),
          width: 600,
        })
      } else {
        message.info('所有识别到的杂质已存在于列表中')
      }
    } catch (error) {
      console.error('自动识别失败', error)
      message.error('自动识别失败，请手动添加')
    } finally {
      setAutoIdentifying(false)
    }
  }

  const handleConfirm = () => {
    if (impurities.length === 0) {
      message.warning('请至少添加一条杂质记录')
      return
    }
    const totalImp = impurities.reduce((s, i) => s + (i.typical_level_pct || 0), 0)
    const maxSingle = Math.max(...impurities.map(i => i.typical_level_pct || 0))

    const study: ImpurityStudy = {
      id: `impurity-${optimizationId}`,
      impurities,
      control_strategy_summary: controlStrategySummary || `共识别${impurities.length}种杂质，其中高风险${impurities.filter(i => i.risk_level === 'high').length}种，已制定相应控制策略。`,
      total_impurities_pct: Math.round(totalImp * 100) / 100,
      max_single_impurity_pct: Math.round(maxSingle * 100) / 100,
      conclusion: studyConclusion || '杂质研究完成，控制策略已制定。',
    }
    onComplete(study)
  }

  const columns = [
    {
      title: '杂质名称',
      dataIndex: 'name',
      key: 'name',
      width: 140,
    },
    {
      title: '类别',
      dataIndex: 'category',
      key: 'category',
      width: 100,
      render: (cat: ImpurityCategory) => {
        const item = categoryMap[cat]
        return item ? <Tag color={item.color}>{item.label}</Tag> : cat
      },
    },
    {
      title: '来源',
      dataIndex: 'source',
      key: 'source',
      width: 150,
    },
    {
      title: 'ICH分类',
      key: 'ich_class',
      width: 140,
      render: (_: unknown, record: Impurity) => {
        if (record.ich_m7_class) {
          const item = m7ClassMap[record.ich_m7_class]
          return item ? <Tag color={item.color}>{item.label}</Tag> : record.ich_m7_class
        }
        if (record.ich_solvent_class) {
          return <Tag color="purple">{record.ich_solvent_class.toUpperCase()}</Tag>
        }
        return '-'
      },
    },
    {
      title: '典型水平(%)',
      dataIndex: 'typical_level_pct',
      key: 'typical_level_pct',
      width: 100,
      render: (v: number) => v != null ? `${v}%` : '-',
    },
    {
      title: '限度(ppm)',
      dataIndex: 'limit_ppm',
      key: 'limit_ppm',
      width: 100,
      render: (v: number) => v != null ? v : '-',
    },
    {
      title: '检测方法',
      dataIndex: 'detection_method',
      key: 'detection_method',
      width: 90,
    },
    {
      title: '控制方式',
      dataIndex: 'control_method',
      key: 'control_method',
      width: 100,
      render: (m: ControlMethod) => {
        const map: Record<ControlMethod, string> = { process_control: '过程控制', release_test: '放行检测', both: '两者兼有' }
        return map[m] || m
      },
    },
    {
      title: '风险',
      dataIndex: 'risk_level',
      key: 'risk_level',
      width: 70,
      render: (level: string) => {
        const item = riskMap[level]
        return item ? <Tag color={item.color}>{item.label}</Tag> : level
      },
    },
    {
      title: '操作',
      key: 'action',
      width: 70,
      render: (_: unknown, record: Impurity) => (
        <Button type="link" size="small" danger icon={<DeleteOutlined />} onClick={() => handleRemoveImpurity(record.id)} />
      ),
    },
  ]

  const highRiskCount = impurities.filter(i => i.risk_level === 'high').length
  const medRiskCount = impurities.filter(i => i.risk_level === 'medium').length
  const totalImp = impurities.reduce((s, i) => s + (i.typical_level_pct || 0), 0)

  return (
    <div>
      <Card>
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={[
            {
              key: 'identification',
              label: <span><BugOutlined /> 2a. 杂质识别</span>,
              children: (
                <div>
                  <Alert
                    title="杂质识别与分析"
                    description="基于DOE优化后的工艺，系统识别工艺杂质、降解杂质、残留溶剂和元素杂质，并进行ICH分类和风险评估。"
                    type="info"
                    showIcon
                    style={{ marginBottom: 16 }}
                  />

                  {doeExperiment && (
                    <Alert
                      title={`上游DOE优化已完成，涉及 ${doeExperiment.factors.length} 个因素、${doeExperiment.runs.filter(r => r.status === 'completed').length} 组实验`}
                      type="success"
                      showIcon
                      style={{ marginBottom: 16 }}
                    />
                  )}

                  <div style={{ marginBottom: 16 }}>
                    <Space>
                      <Button icon={<PlusOutlined />} onClick={() => setShowForm(true)}>➕ 添加杂质</Button>
                      <Button icon={<RobotOutlined />} onClick={handleAutoIdentify} loading={autoIdentifying} type="primary" ghost>🔍 自动识别</Button>
                      <Tag color="blue">工艺杂质: {impurities.filter(i => i.category === 'process').length}</Tag>
                      <Tag color="orange">降解杂质: {impurities.filter(i => i.category === 'degradation').length}</Tag>
                      <Tag color="purple">残留溶剂: {impurities.filter(i => i.category === 'residual_solvent').length}</Tag>
                      <Tag color="red">基因毒性: {impurities.filter(i => i.category === 'genotoxic').length}</Tag>
                    </Space>
                  </div>

                  {showForm && (
                    <Card size="small" style={{ marginBottom: 16, backgroundColor: '#fafafa' }}>
                      <Form form={form} layout="inline" style={{ flexWrap: 'wrap', gap: 8 }}>
                        <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input placeholder="杂质名称" /></Form.Item>
                        <Form.Item name="category" label="类别" initialValue="process">
                          <Select style={{ width: 120 }} options={Object.entries(categoryMap).map(([k, v]) => ({ value: k, label: v.label }))} />
                        </Form.Item>
                        <Form.Item name="source" label="来源"><Input placeholder="杂质来源" /></Form.Item>
                        <Form.Item name="ich_m7_class" label="M7分类">
                          <Select style={{ width: 160 }} allowClear options={Object.entries(m7ClassMap).map(([k, v]) => ({ value: k, label: v.label }))} />
                        </Form.Item>
                        <Form.Item name="ich_solvent_class" label="溶剂分类">
                          <Select style={{ width: 100 }} allowClear options={[
                            { value: 'class1', label: 'Class 1' },
                            { value: 'class2', label: 'Class 2' },
                            { value: 'class3', label: 'Class 3' },
                          ]} />
                        </Form.Item>
                        <Form.Item name="typical_level_pct" label="水平(%)"><InputNumber min={0} max={100} step={0.01} /></Form.Item>
                        <Form.Item name="limit_ppm" label="限度(ppm)"><InputNumber min={0} /></Form.Item>
                        <Form.Item name="detection_method" label="检测方法">
                          <Select style={{ width: 100 }} options={[
                            { value: 'HPLC', label: 'HPLC' },
                            { value: 'GC', label: 'GC' },
                            { value: 'LC-MS', label: 'LC-MS' },
                            { value: 'ICP-MS', label: 'ICP-MS' },
                            { value: 'TLC', label: 'TLC' },
                          ]} />
                        </Form.Item>
                        <Form.Item name="control_method" label="控制方式" initialValue="release_test">
                          <Select style={{ width: 120 }} options={[
                            { value: 'process_control', label: '过程控制' },
                            { value: 'release_test', label: '放行检测' },
                            { value: 'both', label: '两者兼有' },
                          ]} />
                        </Form.Item>
                        <Form.Item name="risk_level" label="风险" initialValue="medium">
                          <Select style={{ width: 80 }} options={[
                            { value: 'low', label: '低' },
                            { value: 'medium', label: '中' },
                            { value: 'high', label: '高' },
                          ]} />
                        </Form.Item>
                        <Form.Item>
                          <Space>
                            <Button type="primary" onClick={handleAddImpurity}>保存</Button>
                            <Button onClick={() => { setShowForm(false); form.resetFields() }}>取消</Button>
                          </Space>
                        </Form.Item>
                      </Form>
                    </Card>
                  )}

                  <Table
                    columns={columns}
                    dataSource={impurities}
                    rowKey="id"
                    pagination={false}
                    size="small"
                    scroll={{ x: 1100 }}
                  />
                </div>
              ),
            },
            {
              key: 'classification',
              label: <span><SafetyOutlined /> 2b. ICH分类</span>,
              children: (
                <div>
                  <Row gutter={16} style={{ marginBottom: 16 }}>
                    <Col span={6}>
                      <Card size="small"><Statistic title="总杂质数" value={impurities.length} /></Card>
                    </Col>
                    <Col span={6}>
                      <Card size="small"><Statistic title="高风险" value={highRiskCount} valueStyle={{ color: highRiskCount > 0 ? '#ff4d4f' : '#52c41a' }} /></Card>
                    </Col>
                    <Col span={6}>
                      <Card size="small"><Statistic title="中风险" value={medRiskCount} valueStyle={{ color: medRiskCount > 0 ? '#faad14' : '#52c41a' }} /></Card>
                    </Col>
                    <Col span={6}>
                      <Card size="small"><Statistic title="总杂质水平" value={totalImp} precision={2} suffix="%" /></Card>
                    </Col>
                  </Row>

                  <Card size="small" title="ICH Q3C 残留溶剂分类" style={{ marginBottom: 16 }}>
                    <Descriptions column={1} size="small">
                      <Descriptions.Item label="Class 1（应避免）">
                        {impurities.filter(i => i.ich_solvent_class === 'class1').map(i => <Tag key={i.id} color="red">{i.name}</Tag>) || '无'}
                      </Descriptions.Item>
                      <Descriptions.Item label="Class 2（应限制）">
                        {impurities.filter(i => i.ich_solvent_class === 'class2').map(i => <Tag key={i.id} color="orange">{i.name} ({i.limit_ppm}ppm)</Tag>) || '无'}
                      </Descriptions.Item>
                      <Descriptions.Item label="Class 3（低毒性）">
                        {impurities.filter(i => i.ich_solvent_class === 'class3').map(i => <Tag key={i.id} color="green">{i.name}</Tag>) || '无'}
                      </Descriptions.Item>
                    </Descriptions>
                  </Card>

                  <Card size="small" title="ICH M7 基因毒性杂质评估" style={{ marginBottom: 16 }}>
                    <Descriptions column={1} size="small">
                      {Object.entries(m7ClassMap).map(([cls, info]) => (
                        <Descriptions.Item key={cls} label={info.label}>
                          {impurities.filter(i => i.ich_m7_class === cls).map(i => (
                            <Tag key={i.id} color={info.color}>{i.name}</Tag>
                          ))}
                          {impurities.filter(i => i.ich_m7_class === cls).length === 0 && <span style={{ color: '#999' }}>无</span>}
                        </Descriptions.Item>
                      ))}
                    </Descriptions>
                  </Card>

                  <Card size="small" title="ICH Q3D 元素杂质">
                    <Alert
                      title="元素杂质评估需根据处方组成、设备、容器密封系统等进行系统评估"
                      description={impurities.filter(i => i.category === 'elemental').length > 0
                        ? `已识别 ${impurities.filter(i => i.category === 'elemental').length} 种元素杂质`
                        : '当前工艺暂未识别元素杂质风险'
                      }
                      type={impurities.filter(i => i.category === 'elemental').length > 0 ? 'warning' : 'success'}
                      showIcon
                    />
                  </Card>
                </div>
              ),
            },
            {
              key: 'control',
              label: <span>🛡️ 2c. 控制策略</span>,
              children: (
                <div>
                  <Card size="small" title="杂质控制策略总览" style={{ marginBottom: 16 }}>
                    <Table
                      dataSource={impurities}
                      rowKey="id"
                      pagination={false}
                      size="small"
                      columns={[
                        { title: '杂质', dataIndex: 'name', width: 140 },
                        { title: '风险', dataIndex: 'risk_level', width: 70, render: (l: string) => { const r = riskMap[l]; return r ? <Tag color={r.color}>{r.label}</Tag> : l } },
                        { title: '控制方式', dataIndex: 'control_method', width: 100, render: (m: ControlMethod) => ({ process_control: '过程控制', release_test: '放行检测', both: '两者兼有' }[m] || m) },
                        { title: '限度(ppm)', dataIndex: 'limit_ppm', width: 100, render: (v: number) => v != null ? v : '-' },
                        { title: '检测方法', dataIndex: 'detection_method', width: 90 },
                      ]}
                    />
                  </Card>

                  <div style={{ marginBottom: 16 }}>
                    <div style={{ fontWeight: 500, marginBottom: 8 }}>控制策略总结</div>
                    <Input.TextArea
                      rows={4}
                      value={controlStrategySummary}
                      onChange={(e) => setControlStrategySummary(e.target.value)}
                      placeholder="描述杂质控制策略的整体方案..."
                    />
                  </div>

                  <div style={{ marginBottom: 16 }}>
                    <div style={{ fontWeight: 500, marginBottom: 8 }}>研究结论</div>
                    <Input.TextArea
                      rows={3}
                      value={studyConclusion}
                      onChange={(e) => setStudyConclusion(e.target.value)}
                      placeholder="杂质研究结论..."
                    />
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
            disabled={impurities.length === 0}
          >
            ✓ 确认并进入下一步（晶型研究）
          </Button>
          <Tag>已识别 {impurities.length} 种杂质</Tag>
        </Space>
      </Card>
    </div>
  )
}
