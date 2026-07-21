'use client'

import { useState } from 'react'
import { Card, Button, Form, Input, InputNumber, Select, App, Descriptions, Alert } from 'antd'
import { CheckCircleOutlined, ExperimentOutlined } from '@ant-design/icons'
import type { LabConfirmationStudy, LabConfirmationBatch, DOEExperiment, QualityStandardSet } from '@/types/rd'
import { AIFileParser } from './AIFileParser'

interface ModuleLabConfirmationProps {
  optimizationId: string
  doeExperiment?: DOEExperiment
  qualityStandardSet?: QualityStandardSet
  initialData?: LabConfirmationStudy
  onComplete: (study: LabConfirmationStudy) => void
}

export function ModuleLabConfirmation({
  optimizationId,
  doeExperiment,
  qualityStandardSet,
  initialData,
  onComplete,
}: ModuleLabConfirmationProps) {
  const { message } = App.useApp()
  const [form] = Form.useForm()
  const [study, setStudy] = useState<LabConfirmationStudy | undefined>(initialData)
  const [editing, setEditing] = useState(!initialData)

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      
      const batch: LabConfirmationBatch = {
        id: `lab-batch-${Date.now()}`,
        batch_no: values.batch_no || `LAB-${new Date().getFullYear()}-${String(Date.now()).slice(-4)}`,
        scale_g: values.scale_g,
        date: values.date || new Date().toISOString().split('T')[0],
        operator: values.operator,
        equipment: values.equipment,
        parameters: {
          temperature: values.temperature,
          time: values.time,
          ratio: values.ratio,
          other: values.other_parameters,
        },
        yield_pct: values.yield_pct,
        purity_pct: values.purity_pct,
        impurities_pct: values.impurities_pct || 0,
        appearance: values.appearance,
        observations: values.observations,
        status: 'completed',
      }

      const newStudy: LabConfirmationStudy = {
        id: `lab-confirmation-${optimizationId}`,
        purpose: values.purpose,
        batch,
        conclusion: values.conclusion,
      }

      setStudy(newStudy)
      setEditing(false)
      message.success('小试工艺确认已完成')
      onComplete(newStudy)
    } catch (error) {
      console.error('Form validation failed:', error)
    }
  }

  const handleEdit = () => {
    setEditing(true)
  }

  // 从DOE最优条件生成默认参数
  const getDefaultParameters = () => {
    if (!doeExperiment?.analysis_result?.optimal_conditions) return {}
    const optimal = doeExperiment.analysis_result.optimal_conditions
    const params: any = {}
    doeExperiment.factors.forEach(f => {
      if (optimal[f.symbol] !== undefined) {
        const key = f.name.includes('温度') ? 'temperature' : 
                   f.name.includes('时间') ? 'time' :
                   f.name.includes('比例') ? 'ratio' : null
        if (key) params[key] = `${optimal[f.symbol]} ${f.unit || ''}`
      }
    })
    return params
  }

  if (!editing && study) {
    return (
      <div>
        <Alert
          type="success"
          showIcon
          icon={<CheckCircleOutlined />}
          title="小试工艺确认已完成"
          description="小试确认批数据已记录，可作为公斤级放大试验方案的依据。"
          style={{ marginBottom: 16 }}
        />

        <Card title="小试确认批信息" style={{ marginBottom: 16 }}>
          <Descriptions bordered column={2}>
            <Descriptions.Item label="批号">{study.batch.batch_no}</Descriptions.Item>
            <Descriptions.Item label="规模">{study.batch.scale_g} g</Descriptions.Item>
            <Descriptions.Item label="日期">{study.batch.date}</Descriptions.Item>
            <Descriptions.Item label="操作人">{study.batch.operator}</Descriptions.Item>
            <Descriptions.Item label="设备">{study.batch.equipment}</Descriptions.Item>
            <Descriptions.Item label="外观">{study.batch.appearance}</Descriptions.Item>
          </Descriptions>
        </Card>

        <Card title="工艺参数" style={{ marginBottom: 16 }}>
          <Descriptions bordered column={2}>
            {study.batch.parameters.temperature && (
              <Descriptions.Item label="反应温度">{study.batch.parameters.temperature}</Descriptions.Item>
            )}
            {study.batch.parameters.time && (
              <Descriptions.Item label="反应时间">{study.batch.parameters.time}</Descriptions.Item>
            )}
            {study.batch.parameters.ratio && (
              <Descriptions.Item label="投料比例">{study.batch.parameters.ratio}</Descriptions.Item>
            )}
            {study.batch.parameters.other && (
              <Descriptions.Item label="其他参数" span={2}>{study.batch.parameters.other}</Descriptions.Item>
            )}
          </Descriptions>
        </Card>

        <Card title="质量结果" style={{ marginBottom: 16 }}>
          <Descriptions bordered column={3}>
            <Descriptions.Item label="收率">{study.batch.yield_pct}%</Descriptions.Item>
            <Descriptions.Item label="纯度">{study.batch.purity_pct}%</Descriptions.Item>
            <Descriptions.Item label="杂质">{study.batch.impurities_pct}%</Descriptions.Item>
          </Descriptions>
        </Card>

        <Card title="确认结论" style={{ marginBottom: 16 }}>
          <div style={{ whiteSpace: 'pre-wrap' }}>{study.conclusion}</div>
        </Card>

        <div style={{ textAlign: 'right' }}>
          <Button icon={<ExperimentOutlined />} onClick={handleEdit}>
            修改小试确认
          </Button>
        </div>
      </div>
    )
  }

  const defaultParams = getDefaultParameters()

  return (
    <div>
      <Alert
        type="info"
        showIcon
        title="小试工艺确认"
        description="在公斤级放大试验前，需要进行至少一批小试工艺确认（g级规模），验证DOE优化参数的可行性，并为放大方案提供依据。"
        style={{ marginBottom: 16 }}
      />


      <AIFileParser
        parseType="lab_confirmation"
        onParseComplete={(data) => {
          // 将AI解析的结果填充到表单
          form.setFieldsValue({
            batch_no: data.batch_no,
            scale_g: data.scale_g,
            date: data.date,
            operator: data.operator,
            equipment: data.equipment,
            temperature: data.temperature,
            time: data.time,
            ratio: data.ratio,
            other_parameters: data.other_parameters,
            yield_pct: data.yield_pct,
            purity_pct: data.purity_pct,
            impurities_pct: data.impurities_pct,
            appearance: data.appearance,
            observations: data.observations,
            conclusion: data.conclusion,
          })
          message.success('AI已自动填充表单，请检查并确认')
        }}
        hint="上传小试实验记录、批记录或工艺规程，AI将自动识别并填充表单"
      />

      <Card title="小试确认批记录">
        <Form
          form={form}
          layout="vertical"
          initialValues={{
            purpose: '验证DOE优化工艺参数的可行性，确认工艺稳定性，为公斤级放大试验提供依据。',
            scale_g: 100,
            temperature: defaultParams.temperature,
            time: defaultParams.time,
            ratio: defaultParams.ratio,
            batch_no: initialData?.batch.batch_no,
            date: initialData?.batch.date,
            operator: initialData?.batch.operator,
            equipment: initialData?.batch.equipment,
            yield_pct: initialData?.batch.yield_pct,
            purity_pct: initialData?.batch.purity_pct,
            impurities_pct: initialData?.batch.impurities_pct,
            appearance: initialData?.batch.appearance,
            observations: initialData?.batch.observations,
            conclusion: initialData?.conclusion,
          }}
        >
          <Form.Item
            name="purpose"
            label="确认目的"
            rules={[{ required: true, message: '请输入确认目的' }]}
          >
            <Input.TextArea rows={2} placeholder="说明本次小试确认的目的" />
          </Form.Item>

          <Form.Item
            name="batch_no"
            label="批号"
            rules={[{ required: true, message: '请输入批号' }]}
          >
            <Input placeholder="如：LAB-2026-001" />
          </Form.Item>

          <Form.Item
            name="scale_g"
            label="规模 (g)"
            rules={[{ required: true, message: '请输入规模' }]}
          >
            <InputNumber min={1} max={10000} style={{ width: '100%' }} placeholder="小试规模（克级）" />
          </Form.Item>

          <Form.Item
            name="date"
            label="日期"
            rules={[{ required: true, message: '请输入日期' }]}
          >
            <Input type="date" />
          </Form.Item>

          <Form.Item
            name="operator"
            label="操作人"
            rules={[{ required: true, message: '请输入操作人' }]}
          >
            <Input placeholder="操作人姓名" />
          </Form.Item>

          <Form.Item
            name="equipment"
            label="设备"
            rules={[{ required: true, message: '请输入设备' }]}
          >
            <Input placeholder="如：100mL三口烧瓶" />
          </Form.Item>

          <Card type="inner" title="工艺参数（基于DOE最优条件）" style={{ marginBottom: 16 }}>
            <Form.Item name="temperature" label="反应温度">
              <Input placeholder="如：70°C" />
            </Form.Item>
            <Form.Item name="time" label="反应时间">
              <Input placeholder="如：4h" />
            </Form.Item>
            <Form.Item name="ratio" label="投料比例">
              <Input placeholder="如：1:1.2" />
            </Form.Item>
            <Form.Item name="other_parameters" label="其他参数">
              <Input.TextArea rows={2} placeholder="其他关键工艺参数" />
            </Form.Item>
          </Card>

          <Card type="inner" title="质量结果" style={{ marginBottom: 16 }}>
            <Form.Item
              name="yield_pct"
              label="收率 (%)"
              rules={[{ required: true, message: '请输入收率' }]}
            >
              <InputNumber min={0} max={100} precision={1} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item
              name="purity_pct"
              label="纯度 (%)"
              rules={[{ required: true, message: '请输入纯度' }]}
            >
              <InputNumber min={0} max={100} precision={2} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="impurities_pct" label="杂质 (%)">
              <InputNumber min={0} max={10} precision={2} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item
              name="appearance"
              label="外观"
              rules={[{ required: true, message: '请输入外观' }]}
            >
              <Input placeholder="如：白色结晶性粉末" />
            </Form.Item>
            <Form.Item name="observations" label="观察记录">
              <Input.TextArea rows={3} placeholder="实验过程中的观察和记录" />
            </Form.Item>
          </Card>

          <Form.Item
            name="conclusion"
            label="确认结论"
            rules={[{ required: true, message: '请输入确认结论' }]}
          >
            <Input.TextArea
              rows={4}
              placeholder="总结小试确认结果，说明工艺参数是否可行，是否存在需要调整的问题，为公斤级放大试验提供建议。"
            />
          </Form.Item>

          <Form.Item>
            <Button type="primary" onClick={handleSubmit} block>
              完成小试工艺确认
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  )
}
