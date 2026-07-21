'use client'

import { useState } from 'react'
import { Card, Button, Space, Tag, Table, Form, Input, Select, App, Tabs, Alert, Row, Col, Statistic } from 'antd'
import { CheckCircleOutlined, PlusOutlined, DeleteOutlined, SafetyCertificateOutlined } from '@ant-design/icons'
import type { QualityStandardSet, QualityStandard, TestMethod, DOEExperiment, ImpurityStudy, CrystalFormStudy } from '@/types/rd'

interface ModuleQualityStandardProps {
  optimizationId: string
  doeExperiment?: DOEExperiment
  impurityStudy?: ImpurityStudy
  crystalFormStudy?: CrystalFormStudy
  initialData?: QualityStandardSet
  onComplete: (standards: QualityStandardSet) => void
}

const testMethodMap: Record<TestMethod, string> = {
  hplc: 'HPLC',
  gc: 'GC',
  kf: 'KF(卡尔费休)',
  particle_size: '粒度分析',
  melting_point: '熔点',
  xrd: 'XRD',
  titration: '滴定',
  ph: 'pH值',
  visual: '外观',
  other: '其他',
}

const categoryMap: Record<string, { color: string; label: string }> = {
  identity: { color: 'blue', label: '鉴别' },
  assay: { color: 'green', label: '含量' },
  impurity: { color: 'orange', label: '杂质' },
  physical: { color: 'purple', label: '物理性质' },
  residual: { color: 'cyan', label: '残留' },
  other: { color: 'default', label: '其他' },
}

export function ModuleQualityStandard({ optimizationId, doeExperiment, impurityStudy, crystalFormStudy, initialData, onComplete }: ModuleQualityStandardProps) {
  const { message } = App.useApp()
  const [activeTab, setActiveTab] = useState('methods')
  const [standards, setStandards] = useState<QualityStandard[]>(initialData?.standards || [
    { id: 'qs-1', test_item: '性状/外观', test_method: 'visual', specification: '白色至类白色结晶性粉末', category: 'physical' },
    { id: 'qs-2', test_item: '鉴别(IR)', test_method: 'other', specification: '与对照品图谱一致', method_reference: 'ChP 通则0402', category: 'identity' },
    { id: 'qs-3', test_item: '含量(HPLC)', test_method: 'hplc', specification: '98.0%~102.0%', method_reference: 'ChP 通则0512', category: 'assay' },
    { id: 'qs-4', test_item: '有关物质', test_method: 'hplc', specification: '单个杂质≤0.10%，总杂质≤0.30%', method_reference: 'ICH Q3A(R2)', category: 'impurity' },
    { id: 'qs-5', test_item: '残留溶剂', test_method: 'gc', specification: '符合ICH Q3C限度', method_reference: 'ICH Q3C(R8)', category: 'residual' },
    { id: 'qs-6', test_item: '水分', test_method: 'kf', specification: '≤0.5%', category: 'physical' },
    { id: 'qs-7', test_item: '晶型', test_method: 'xrd', specification: '与对照图谱一致(Form A)', category: 'physical' },
    { id: 'qs-8', test_item: '粒度分布', test_method: 'particle_size', specification: 'D90≤50μm', category: 'physical' },
  ])
  const [shelfLife, setShelfLife] = useState(initialData?.shelf_life_proposal || '24个月（25°C/60%RH密封保存）')
  const [storageCondition, setStorageCondition] = useState(initialData?.storage_condition || '密封，避光，25°C以下保存')
  const [packaging, setPackaging] = useState(initialData?.packaging || '双层PE袋+铝箔袋密封包装')
  const [conclusion, setConclusion] = useState(initialData?.conclusion || '')
  const [showForm, setShowForm] = useState(false)
  const [form] = Form.useForm()

  const handleAddStandard = async () => {
    try {
      const values = await form.validateFields()
      const newStandard: QualityStandard = {
        id: `qs-${Date.now()}`,
        test_item: values.test_item,
        test_method: values.test_method,
        method_reference: values.method_reference,
        specification: values.specification,
        justification: values.justification,
        category: values.category,
      }
      setStandards([...standards, newStandard])
      form.resetFields()
      setShowForm(false)
      message.success('检测项目已添加')
    } catch {}
  }

  const handleRemoveStandard = (id: string) => {
    setStandards(prev => prev.filter(s => s.id !== id))
  }

  const handleConfirm = () => {
    if (standards.length === 0) {
      message.warning('请至少添加一条质量标准')
      return
    }
    const standardSet: QualityStandardSet = {
      id: `quality-${optimizationId}`,
      standards,
      shelf_life_proposal: shelfLife,
      storage_condition: storageCondition,
      packaging,
      conclusion: conclusion || `质量标准草案已建立，共${standards.length}项检测指标。`,
    }
    onComplete(standardSet)
  }

  const columns = [
    {
      title: '检测项目',
      dataIndex: 'test_item',
      key: 'test_item',
      width: 140,
    },
    {
      title: '类别',
      dataIndex: 'category',
      key: 'category',
      width: 80,
      render: (cat: string) => {
        const item = categoryMap[cat]
        return item ? <Tag color={item.color}>{item.label}</Tag> : cat
      },
    },
    {
      title: '检测方法',
      dataIndex: 'test_method',
      key: 'test_method',
      width: 120,
      render: (m: TestMethod) => testMethodMap[m] || m,
    },
    {
      title: '方法依据',
      dataIndex: 'method_reference',
      key: 'method_reference',
      width: 140,
      render: (v: string) => v || '-',
    },
    {
      title: '质量标准',
      dataIndex: 'specification',
      key: 'specification',
      width: 220,
    },
    {
      title: '制定依据',
      dataIndex: 'justification',
      key: 'justification',
      width: 140,
      render: (v: string) => v || '-',
    },
    {
      title: '操作',
      key: 'action',
      width: 60,
      render: (_: unknown, record: QualityStandard) => (
        <Button type="link" size="small" danger icon={<DeleteOutlined />} onClick={() => handleRemoveStandard(record.id)} />
      ),
    },
  ]

  return (
    <div>
      <Card>
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={[
            {
              key: 'methods',
              label: <span><SafetyCertificateOutlined /> 4a. 检测方法</span>,
              children: (
                <div>
                  <Alert
                    title="质量标准建立"
                    description="基于DOE优化数据、杂质研究和晶型研究结果，制定检测方法和质量标准。"
                    type="info"
                    showIcon
                    style={{ marginBottom: 16 }}
                  />

                  {/* 上游数据汇总 */}
                  <Row gutter={16} style={{ marginBottom: 16 }}>
                    <Col span={8}>
                      <Card size="small">
                        <Statistic title="DOE优化" value={doeExperiment ? '已完成' : '未进行'} valueStyle={{ fontSize: 16, color: doeExperiment ? '#52c41a' : '#999' }} />
                      </Card>
                    </Col>
                    <Col span={8}>
                      <Card size="small">
                        <Statistic title="杂质研究" value={impurityStudy ? `${impurityStudy.impurities.length}种杂质` : '未进行'} valueStyle={{ fontSize: 16, color: impurityStudy ? '#52c41a' : '#999' }} />
                      </Card>
                    </Col>
                    <Col span={8}>
                      <Card size="small">
                        <Statistic title="晶型研究" value={crystalFormStudy ? `${crystalFormStudy.records.length}种晶型` : '未进行'} valueStyle={{ fontSize: 16, color: crystalFormStudy ? '#52c41a' : '#999' }} />
                      </Card>
                    </Col>
                  </Row>

                  <div style={{ marginBottom: 16 }}>
                    <Space>
                      <Button icon={<PlusOutlined />} onClick={() => setShowForm(true)}>➕ 添加检测项目</Button>
                      <Tag>共 {standards.length} 项</Tag>
                    </Space>
                  </div>

                  {showForm && (
                    <Card size="small" style={{ marginBottom: 16, backgroundColor: '#fafafa' }}>
                      <Form form={form} layout="inline" style={{ flexWrap: 'wrap', gap: 8 }}>
                        <Form.Item name="test_item" label="检测项目" rules={[{ required: true }]}><Input placeholder="如 含量" /></Form.Item>
                        <Form.Item name="category" label="类别" initialValue="assay">
                          <Select style={{ width: 100 }} options={Object.entries(categoryMap).map(([k, v]) => ({ value: k, label: v.label }))} />
                        </Form.Item>
                        <Form.Item name="test_method" label="方法" initialValue="hplc">
                          <Select style={{ width: 130 }} options={Object.entries(testMethodMap).map(([k, v]) => ({ value: k, label: v }))} />
                        </Form.Item>
                        <Form.Item name="specification" label="标准" rules={[{ required: true }]}><Input placeholder="如 98.0%~102.0%" style={{ width: 200 }} /></Form.Item>
                        <Form.Item name="method_reference" label="依据"><Input placeholder="如 ChP/ICH" /></Form.Item>
                        <Form.Item name="justification" label="说明"><Input placeholder="制定依据" /></Form.Item>
                        <Form.Item>
                          <Space>
                            <Button type="primary" onClick={handleAddStandard}>保存</Button>
                            <Button onClick={() => { setShowForm(false); form.resetFields() }}>取消</Button>
                          </Space>
                        </Form.Item>
                      </Form>
                    </Card>
                  )}

                  <Table
                    columns={columns}
                    dataSource={standards}
                    rowKey="id"
                    pagination={false}
                    size="small"
                    scroll={{ x: 900 }}
                  />
                </div>
              ),
            },
            {
              key: 'limits',
              label: <span>📏 4b. 杂质限度</span>,
              children: (
                <div>
                  <Alert
                    title="杂质限度制定"
                    description="基于ICH Q3A(R2)/Q3B(R2)指导原则，结合实验数据和安全性评估制定杂质限度。"
                    type="info"
                    showIcon
                    style={{ marginBottom: 16 }}
                  />

                  <Card size="small" title="杂质限度参考（ICH Q3A/Q3B）" style={{ marginBottom: 16 }}>
                    <Table
                      dataSource={[
                        { item: '鉴定限度', daily_dose: '≤2g/天', threshold: '0.05%', reference: 'ICH Q3A(R2)' },
                        { item: '界定限度', daily_dose: '≤2g/天', threshold: '0.15%', reference: 'ICH Q3A(R2)' },
                        { item: '报告限度', daily_dose: '≤2g/天', threshold: '0.05%', reference: 'ICH Q3A(R2)' },
                      ]}
                      columns={[
                        { title: '项目', dataIndex: 'item', width: 120 },
                        { title: '日剂量', dataIndex: 'daily_dose', width: 100 },
                        { title: '限度', dataIndex: 'threshold', width: 80 },
                        { title: '依据', dataIndex: 'reference', width: 140 },
                      ]}
                      pagination={false}
                      size="small"
                    />
                  </Card>

                  {impurityStudy && (
                    <Card size="small" title="基于杂质研究的限度建议">
                      <Table
                        dataSource={impurityStudy.impurities}
                        rowKey="id"
                        pagination={false}
                        size="small"
                        columns={[
                          { title: '杂质', dataIndex: 'name', width: 140 },
                          { title: '典型水平(%)', dataIndex: 'typical_level_pct', width: 100, render: (v: number) => v != null ? `${v}%` : '-' },
                          { title: '建议限度(ppm)', dataIndex: 'limit_ppm', width: 120, render: (v: number) => v != null ? v : '-' },
                          { title: '风险', dataIndex: 'risk_level', width: 70, render: (l: string) => <Tag color={l === 'high' ? 'red' : l === 'medium' ? 'orange' : 'green'}>{l === 'high' ? '高' : l === 'medium' ? '中' : '低'}</Tag> },
                        ]}
                      />
                    </Card>
                  )}
                </div>
              ),
            },
            {
              key: 'release',
              label: <span>📋 4c. 放行标准</span>,
              children: (
                <div>
                  <Card size="small" title="质量标准草案" style={{ marginBottom: 16 }}>
                    <Table
                      dataSource={standards}
                      rowKey="id"
                      pagination={false}
                      size="small"
                      columns={[
                        { title: '序号', key: 'no', width: 50, render: (_: unknown, __: unknown, i: number) => i + 1 },
                        { title: '检测项目', dataIndex: 'test_item', width: 140 },
                        { title: '方法', dataIndex: 'test_method', width: 100, render: (m: TestMethod) => testMethodMap[m] || m },
                        { title: '标准', dataIndex: 'specification', width: 220 },
                      ]}
                    />
                  </Card>

                  <Row gutter={16} style={{ marginBottom: 16 }}>
                    <Col span={8}>
                      <div style={{ fontWeight: 500, marginBottom: 8 }}>拟定有效期</div>
                      <Input value={shelfLife} onChange={(e) => setShelfLife(e.target.value)} />
                    </Col>
                    <Col span={8}>
                      <div style={{ fontWeight: 500, marginBottom: 8 }}>贮藏条件</div>
                      <Input value={storageCondition} onChange={(e) => setStorageCondition(e.target.value)} />
                    </Col>
                    <Col span={8}>
                      <div style={{ fontWeight: 500, marginBottom: 8 }}>包装方式</div>
                      <Input value={packaging} onChange={(e) => setPackaging(e.target.value)} />
                    </Col>
                  </Row>

                  <div style={{ marginBottom: 16 }}>
                    <div style={{ fontWeight: 500, marginBottom: 8 }}>结论</div>
                    <Input.TextArea
                      rows={3}
                      value={conclusion}
                      onChange={(e) => setConclusion(e.target.value)}
                      placeholder="质量标准建立结论..."
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
            disabled={standards.length === 0}
          >
            ✓ 确认并进入下一步（公斤级放大）
          </Button>
          <Tag>已制定 {standards.length} 项质量标准</Tag>
        </Space>
      </Card>
    </div>
  )
}
