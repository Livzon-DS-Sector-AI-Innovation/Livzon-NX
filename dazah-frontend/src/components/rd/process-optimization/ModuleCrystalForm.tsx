'use client'

import { useState } from 'react'
import { Card, Button, Space, Tag, Table, Form, Input, Select, App, Tabs, Alert, Row, Col, Statistic, Radio } from 'antd'
import { CheckCircleOutlined, PlusOutlined, DeleteOutlined, ExperimentOutlined } from '@ant-design/icons'
import type { CrystalFormStudy, CrystalFormRecord, CrystalFormType } from '@/types/rd'

interface ModuleCrystalFormProps {
  optimizationId: string
  initialData?: CrystalFormStudy
  onComplete: (study: CrystalFormStudy) => void
}

const formTypeMap: Record<CrystalFormType, { color: string; label: string }> = {
  polymorph: { color: 'blue', label: '多晶型' },
  hydrate: { color: 'cyan', label: '水合物' },
  solvate: { color: 'purple', label: '溶剂化物' },
  salt: { color: 'orange', label: '盐型' },
  amorphous: { color: 'default', label: '无定形' },
}

export function ModuleCrystalForm({ optimizationId, initialData, onComplete }: ModuleCrystalFormProps) {
  const { message } = App.useApp()
  const [activeTab, setActiveTab] = useState('screening')
  const [records, setRecords] = useState<CrystalFormRecord[]>(initialData?.records || [
    {
      id: 'cf-1',
      form_name: 'Form A',
      form_type: 'polymorph',
      solvent_system: '乙醇/水 (8:2)',
      temperature_condition: '室温缓慢挥发',
      cooling_rate: '自然冷却',
      crystallization_method: '溶液结晶',
      xrd_peaks: '2θ = 7.2, 14.5, 21.8, 28.3°',
      stability_assessment: '室温稳定，6个月无转变',
      is_preferred: true,
      notes: '热力学稳定晶型，适合开发',
    },
    {
      id: 'cf-2',
      form_name: 'Form B',
      form_type: 'polymorph',
      solvent_system: '丙酮',
      temperature_condition: '冷却结晶 (50°C→0°C)',
      cooling_rate: '快速冷却 (10°C/h)',
      crystallization_method: '冷却结晶',
      xrd_peaks: '2θ = 6.8, 13.2, 19.7, 25.1°',
      stability_assessment: '亚稳态，40°C/75%RH下7天转变为Form A',
      is_preferred: false,
      notes: '亚稳态晶型，溶解度较高但不稳定',
    },
    {
      id: 'cf-3',
      form_name: '盐酸盐',
      form_type: 'salt',
      solvent_system: '乙醇 + HCl(气)',
      temperature_condition: '0°C析晶',
      crystallization_method: '成盐结晶',
      xrd_peaks: '2θ = 11.3, 16.8, 22.5°',
      stability_assessment: '吸湿性较强',
      is_preferred: false,
      notes: '吸湿性强，不适合开发',
    },
  ])
  const [preferredFormId, setPreferredFormId] = useState(initialData?.preferred_form?.id || records.find(r => r.is_preferred)?.id || '')
  const [saltScreeningResults, setSaltScreeningResults] = useState(initialData?.salt_screening_results || '')
  const [studyConclusion, setStudyConclusion] = useState(initialData?.conclusion || '')
  const [showForm, setShowForm] = useState(false)
  const [form] = Form.useForm()

  const handleAddRecord = async () => {
    try {
      const values = await form.validateFields()
      const newRecord: CrystalFormRecord = {
        id: `cf-${Date.now()}`,
        form_name: values.form_name,
        form_type: values.form_type,
        solvent_system: values.solvent_system,
        temperature_condition: values.temperature_condition,
        cooling_rate: values.cooling_rate,
        crystallization_method: values.crystallization_method,
        xrd_peaks: values.xrd_peaks,
        stability_assessment: values.stability_assessment,
        is_preferred: false,
        notes: values.notes,
      }
      setRecords([...records, newRecord])
      form.resetFields()
      setShowForm(false)
      message.success('晶型记录已添加')
    } catch {}
  }

  const handleRemoveRecord = (id: string) => {
    setRecords(prev => prev.filter(r => r.id !== id))
    if (preferredFormId === id) setPreferredFormId('')
  }

  const handleSetPreferred = (id: string) => {
    setPreferredFormId(id)
    message.success('已设为推荐晶型')
  }

  const handleConfirm = () => {
    if (records.length === 0) {
      message.warning('请至少添加一条晶型记录')
      return
    }
    const preferred = records.find(r => r.id === preferredFormId)
    const study: CrystalFormStudy = {
      id: `crystal-${optimizationId}`,
      records: records.map(r => ({ ...r, is_preferred: r.id === preferredFormId })),
      preferred_form: preferred,
      salt_screening_results: saltScreeningResults,
      conclusion: studyConclusion || `晶型筛选完成，共筛选${records.length}种晶型/盐型，推荐${preferred?.form_name || '最优晶型'}。`,
    }
    onComplete(study)
  }

  const columns = [
    { title: '晶型名称', dataIndex: 'form_name', key: 'form_name', width: 100 },
    {
      title: '类型',
      dataIndex: 'form_type',
      key: 'form_type',
      width: 90,
      render: (t: CrystalFormType) => {
        const item = formTypeMap[t]
        return item ? <Tag color={item.color}>{item.label}</Tag> : t
      },
    },
    { title: '溶剂体系', dataIndex: 'solvent_system', key: 'solvent_system', width: 140 },
    { title: '温度条件', dataIndex: 'temperature_condition', key: 'temperature_condition', width: 140 },
    { title: '结晶方法', dataIndex: 'crystallization_method', key: 'crystallization_method', width: 100 },
    { title: 'XRD特征峰', dataIndex: 'xrd_peaks', key: 'xrd_peaks', width: 180, render: (v: string) => <span style={{ fontSize: 12 }}>{v || '-'}</span> },
    { title: '稳定性评估', dataIndex: 'stability_assessment', key: 'stability_assessment', width: 180, render: (v: string) => <span style={{ fontSize: 12 }}>{v || '-'}</span> },
    {
      title: '推荐',
      key: 'preferred',
      width: 80,
      render: (_: unknown, record: CrystalFormRecord) => (
        <Radio checked={record.id === preferredFormId} onChange={() => handleSetPreferred(record.id)} />
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 60,
      render: (_: unknown, record: CrystalFormRecord) => (
        <Button type="link" size="small" danger icon={<DeleteOutlined />} onClick={() => handleRemoveRecord(record.id)} />
      ),
    },
  ]

  const preferredForm = records.find(r => r.id === preferredFormId)

  return (
    <div>
      <Card>
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={[
            {
              key: 'screening',
              label: <span><ExperimentOutlined /> 3a. 晶型筛选</span>,
              children: (
                <div>
                  <Alert
                    title="晶型/盐型筛选"
                    description="通过不同溶剂体系、温度条件、冷却速率等筛选晶型，记录XRD特征峰和稳定性评估结果。"
                    type="info"
                    showIcon
                    style={{ marginBottom: 16 }}
                  />

                  <div style={{ marginBottom: 16 }}>
                    <Space>
                      <Button icon={<PlusOutlined />} onClick={() => setShowForm(true)}>➕ 添加晶型记录</Button>
                      <Tag>共 {records.length} 种晶型/盐型</Tag>
                      {preferredForm && <Tag color="green">推荐: {preferredForm.form_name}</Tag>}
                    </Space>
                  </div>

                  {showForm && (
                    <Card size="small" style={{ marginBottom: 16, backgroundColor: '#fafafa' }}>
                      <Form form={form} layout="inline" style={{ flexWrap: 'wrap', gap: 8 }}>
                        <Form.Item name="form_name" label="名称" rules={[{ required: true }]}><Input placeholder="如 Form A" /></Form.Item>
                        <Form.Item name="form_type" label="类型" initialValue="polymorph">
                          <Select style={{ width: 110 }} options={Object.entries(formTypeMap).map(([k, v]) => ({ value: k, label: v.label }))} />
                        </Form.Item>
                        <Form.Item name="solvent_system" label="溶剂体系"><Input placeholder="如 乙醇/水" /></Form.Item>
                        <Form.Item name="temperature_condition" label="温度条件"><Input placeholder="如 室温挥发" /></Form.Item>
                        <Form.Item name="cooling_rate" label="冷却速率"><Input placeholder="如 自然冷却" /></Form.Item>
                        <Form.Item name="crystallization_method" label="结晶方法">
                          <Select style={{ width: 120 }} options={[
                            { value: '溶液结晶', label: '溶液结晶' },
                            { value: '冷却结晶', label: '冷却结晶' },
                            { value: '蒸发结晶', label: '蒸发结晶' },
                            { value: '反溶剂结晶', label: '反溶剂结晶' },
                            { value: '成盐结晶', label: '成盐结晶' },
                            { value: '研磨', label: '研磨' },
                          ]} />
                        </Form.Item>
                        <Form.Item name="xrd_peaks" label="XRD特征峰"><Input placeholder="2θ = ..." /></Form.Item>
                        <Form.Item name="stability_assessment" label="稳定性"><Input placeholder="稳定性评估" /></Form.Item>
                        <Form.Item name="notes" label="备注"><Input /></Form.Item>
                        <Form.Item>
                          <Space>
                            <Button type="primary" onClick={handleAddRecord}>保存</Button>
                            <Button onClick={() => { setShowForm(false); form.resetFields() }}>取消</Button>
                          </Space>
                        </Form.Item>
                      </Form>
                    </Card>
                  )}

                  <Table
                    columns={columns}
                    dataSource={records}
                    rowKey="id"
                    pagination={false}
                    size="small"
                    scroll={{ x: 1200 }}
                  />
                </div>
              ),
            },
            {
              key: 'analysis',
              label: <span>🔬 3b. 分析表征</span>,
              children: (
                <div>
                  <Row gutter={16} style={{ marginBottom: 16 }}>
                    <Col span={8}>
                      <Card size="small"><Statistic title="筛选晶型数" value={records.filter(r => r.form_type === 'polymorph').length} /></Card>
                    </Col>
                    <Col span={8}>
                      <Card size="small"><Statistic title="筛选盐型数" value={records.filter(r => r.form_type === 'salt').length} /></Card>
                    </Col>
                    <Col span={8}>
                      <Card size="small"><Statistic title="稳定晶型" value={records.filter(r => r.stability_assessment?.includes('稳定')).length} /></Card>
                    </Col>
                  </Row>

                  {records.map(record => (
                    <Card
                      key={record.id}
                      size="small"
                      title={
                        <Space>
                          <span>{record.form_name}</span>
                          <Tag color={formTypeMap[record.form_type]?.color}>{formTypeMap[record.form_type]?.label}</Tag>
                          {record.id === preferredFormId && <Tag color="green">推荐</Tag>}
                        </Space>
                      }
                      style={{ marginBottom: 12 }}
                    >
                      <Row gutter={16}>
                        <Col span={12}>
                          <div style={{ marginBottom: 8 }}><strong>溶剂体系：</strong>{record.solvent_system}</div>
                          <div style={{ marginBottom: 8 }}><strong>温度条件：</strong>{record.temperature_condition}</div>
                          <div style={{ marginBottom: 8 }}><strong>冷却速率：</strong>{record.cooling_rate || '-'}</div>
                          <div style={{ marginBottom: 8 }}><strong>结晶方法：</strong>{record.crystallization_method}</div>
                        </Col>
                        <Col span={12}>
                          <div style={{ marginBottom: 8 }}><strong>XRD特征峰：</strong></div>
                          <div style={{ fontSize: 12, fontFamily: 'monospace', marginBottom: 8, padding: 8, background: '#f5f5f5', borderRadius: 4 }}>{record.xrd_peaks || '未记录'}</div>
                          <div style={{ marginBottom: 8 }}><strong>稳定性评估：</strong></div>
                          <div style={{ fontSize: 13, color: '#555' }}>{record.stability_assessment || '未评估'}</div>
                        </Col>
                      </Row>
                      {record.notes && <div style={{ marginTop: 8, fontSize: 13, color: '#666' }}><strong>备注：</strong>{record.notes}</div>}
                    </Card>
                  ))}
                </div>
              ),
            },
            {
              key: 'recommendation',
              label: <span>🎯 3c. 工艺推荐</span>,
              children: (
                <div>
                  {preferredForm ? (
                    <Alert
                      title={`推荐晶型：${preferredForm.form_name}`}
                      description={
                        <div>
                          <div>类型：{formTypeMap[preferredForm.form_type]?.label}</div>
                          <div>结晶条件：{preferredForm.solvent_system}，{preferredForm.temperature_condition}</div>
                          <div>结晶方法：{preferredForm.crystallization_method}</div>
                          <div>稳定性：{preferredForm.stability_assessment}</div>
                        </div>
                      }
                      type="success"
                      showIcon
                      style={{ marginBottom: 16 }}
                    />
                  ) : (
                    <Alert title="请在晶型筛选中选择推荐晶型" type="warning" showIcon style={{ marginBottom: 16 }} />
                  )}

                  <div style={{ marginBottom: 16 }}>
                    <div style={{ fontWeight: 500, marginBottom: 8 }}>盐型筛选结果</div>
                    <Input.TextArea
                      rows={3}
                      value={saltScreeningResults}
                      onChange={(e) => setSaltScreeningResults(e.target.value)}
                      placeholder="盐型筛选实验结果总结..."
                    />
                  </div>

                  <div style={{ marginBottom: 16 }}>
                    <div style={{ fontWeight: 500, marginBottom: 8 }}>研究结论</div>
                    <Input.TextArea
                      rows={3}
                      value={studyConclusion}
                      onChange={(e) => setStudyConclusion(e.target.value)}
                      placeholder="晶型研究结论..."
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
            disabled={records.length === 0}
          >
            ✓ 确认并进入下一步（质量标准）
          </Button>
          <Tag>已筛选 {records.length} 种晶型</Tag>
        </Space>
      </Card>
    </div>
  )
}
