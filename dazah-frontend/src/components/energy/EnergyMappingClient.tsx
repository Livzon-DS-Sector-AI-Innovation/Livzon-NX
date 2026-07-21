'use client'

import { DeleteOutlined, EyeOutlined, PlusOutlined, SaveOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, App, Button, Card, Empty, Form, Input, InputNumber, Select, Space, Switch, Table, Tag } from 'antd'
import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'
import { previewEnergyMapping, saveEnergyMapping } from '@/actions/energy'
import {
  fetchEnergyMapping,
  fetchEnergySources,
  type EnergyMappingInput,
  type EnergyMappingPreview,
} from '@/lib/api/energy'
import { notifyEnergySourcesUpdated } from '@/lib/energy-events'

type MappingFormValues = EnergyMappingInput & { dimensions_json?: string }
type SourceRole = NonNullable<EnergyMappingInput['source_role']>

const WORKSHOP_SHEETS = /^\d{3}(?:-\d+)?车间$/
const ENERGY_SUMMARY_SHEETS = new Set(['电量', '饮用水量', '蒸汽量', '冰水量', '空气量', '循环水量'])

const sourceRoleOptions: Array<{ value: SourceRole; label: string }> = [
  { value: 'workshop_detail', label: '车间明细（默认统计）' },
  { value: 'shared_detail', label: '共享明细（默认统计）' },
  { value: 'energy_summary', label: '能源分表（只核对）' },
  { value: 'daily_summary', label: '日总量（只核对）' },
]

const sourceRoleHelp: Record<SourceRole, string> = {
  workshop_detail: '车间明细会进入能源总览；建议将“车间”固定为当前工作表标题。',
  shared_detail: '无车间归属但属于独立来源的公共区域明细会进入能源总览。',
  energy_summary: '按能源类别汇总的工作表会保存为核对数据，不会与车间明细重复相加。',
  daily_summary: '全厂日总量会保存为核对数据，不会与分表、车间明细重复相加。',
}

function inferSourceRole(title: string): SourceRole {
  if (title === '日总量') return 'daily_summary'
  if (ENERGY_SUMMARY_SHEETS.has(title)) return 'energy_summary'
  return WORKSHOP_SHEETS.test(title) ? 'workshop_detail' : 'shared_detail'
}

function asPayload(values: MappingFormValues): EnergyMappingInput {
  let dimensions: Record<string, string> = {}
  if (values.dimensions_json?.trim()) {
    try {
      const parsed: unknown = JSON.parse(values.dimensions_json)
      if (
        !parsed
        || Array.isArray(parsed)
        || typeof parsed !== 'object'
        || Object.entries(parsed).some(([key, value]) => !key.trim() || typeof value !== 'string' || !value.trim())
      ) {
        throw new Error()
      }
      dimensions = parsed as Record<string, string>
    } catch {
      throw new Error('维度映射必须是 JSON 对象，且维度名和列名不能为空')
    }
  }
  const payload: EnergyMappingInput = {
    is_enabled: values.is_enabled ?? false,
    source_role: values.source_role ?? 'workshop_detail',
    header_row: values.header_row ?? 1,
    date_column: values.date_column || null,
    date_format: values.date_format || null,
    dimensions,
    metrics: values.metrics ?? [],
  }
  if (payload.is_enabled && !payload.date_column) {
    throw new Error('启用分析时必须选择日期列')
  }
  if (payload.is_enabled && !payload.metrics?.length) {
    throw new Error('启用分析时必须至少添加一个能源指标')
  }
  if (payload.metrics?.some((metric) => metric.value_semantics === 'cumulative' && !metric.meter_key_column)) {
    throw new Error('累计表底指标必须选择计量点列')
  }
  return payload
}

export function EnergyMappingClient({ sheetId }: { sheetId: string }) {
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const [preview, setPreview] = useState<EnergyMappingPreview | null>(null)
  const [form] = Form.useForm<MappingFormValues>()
  const sourcesQuery = useQuery({ queryKey: ['energy-sources'], queryFn: () => fetchEnergySources() })
  const mappingQuery = useQuery({ queryKey: ['energy-mapping', sheetId], queryFn: () => fetchEnergyMapping(sheetId) })
  const sheet = useMemo(
    () => sourcesQuery.data?.find((item) => item.id === sheetId),
    [sourcesQuery.data, sheetId],
  )
  const columnOptions = (sheet?.headers ?? []).filter(Boolean).map((value) => ({ value, label: value }))
  const sourceRole = Form.useWatch('source_role', form) ?? (sheet ? inferSourceRole(sheet.title) : 'workshop_detail')

  useEffect(() => {
    const mapping = mappingQuery.data
    if (!mapping) return
    form.setFieldsValue({
      is_enabled: mapping.is_enabled,
      source_role: mapping.source_role,
      header_row: mapping.header_row,
      date_column: mapping.date_column,
      date_format: mapping.date_format,
      dimensions_json: JSON.stringify(mapping.dimensions, null, 2),
      metrics: mapping.metrics,
    })
  }, [form, mappingQuery.data])

  useEffect(() => {
    if (mappingQuery.data || !sheet || form.isFieldsTouched()) return
    const inferredRole = inferSourceRole(sheet.title)
    form.setFieldsValue({
      source_role: inferredRole,
      dimensions_json: inferredRole === 'workshop_detail'
        ? JSON.stringify({ 车间: '$sheet_title' }, null, 2)
        : undefined,
    })
  }, [form, mappingQuery.data, sheet])

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ['energy-mapping', sheetId] })
    void queryClient.invalidateQueries({ queryKey: ['energy-sources'] })
    void queryClient.invalidateQueries({ queryKey: ['energy-overview'] })
  }
  const previewMutation = useMutation({
    mutationFn: (payload: EnergyMappingInput) => previewEnergyMapping(sheetId, payload),
    onSuccess: (data) => setPreview(data),
    onError: (error: Error) => message.error(error.message),
  })
  const saveMutation = useMutation({
    mutationFn: (payload: EnergyMappingInput) => saveEnergyMapping(sheetId, payload),
    onSuccess: () => {
      message.success('字段映射已保存并回算快照数据')
      refresh()
      notifyEnergySourcesUpdated()
    },
    onError: (error: Error) => message.error(error.message),
  })

  if (sourcesQuery.isLoading) return <main style={{ padding: 32 }}>正在读取工作表…</main>
  if (!sheet) {
    return (
      <main style={{ maxWidth: 900, margin: '0 auto', padding: '48px 32px' }}>
        <Empty description="未找到该来源工作表。请先完成来源同步。">
          <Link href="/energy/sources">返回来源管理</Link>
        </Empty>
      </main>
    )
  }

  const submit = (values: MappingFormValues, action: 'preview' | 'save') => {
    try {
      const payload = asPayload(values)
      if (action === 'preview') previewMutation.mutate(payload)
      else saveMutation.mutate(payload)
    } catch (error) {
      message.error((error as Error).message)
    }
  }

  return (
    <main style={{ maxWidth: 1100, margin: '0 auto', padding: '28px 32px 48px' }}>
      <Link href="/energy/sources" style={{ color: '#0075de' }}>← 返回来源管理</Link>
      <div style={{ marginTop: 16 }}>
        <h1 style={{ margin: 0, color: '#1a1a1a', fontSize: 28, fontWeight: 600 }}>{sheet.title} 字段映射</h1>
        <p style={{ margin: '6px 0 0', color: '#787671' }}>{sheet.document_title} · {sheet.period_month || '未分类月份'} · {sheet.headers.length} 个已发现字段</p>
      </div>

      <Card style={{ marginTop: 24 }}>
        <Form
          form={form}
          layout="vertical"
          initialValues={{ is_enabled: false, source_role: 'workshop_detail', header_row: 1, metrics: [] }}
          onFinish={(values) => submit(values, 'save')}
        >
          <Space size="large" align="start" wrap>
            <Form.Item label="纳入分析" name="is_enabled" valuePropName="checked">
              <Switch checkedChildren="启用" unCheckedChildren="仅归档" />
            </Form.Item>
            <Form.Item label="工作表角色" name="source_role" extra="角色决定是否进入默认总览。">
              <Select options={sourceRoleOptions} style={{ width: 220 }} />
            </Form.Item>
            <Form.Item label="表头行" name="header_row" rules={[{ required: true }]}>
              <InputNumber min={1} max={100} style={{ width: 120 }} />
            </Form.Item>
            <Form.Item
              label="日期列"
              name="date_column"
              dependencies={['is_enabled']}
              extra="启用分析时必填；仅归档可以留空。"
              rules={[
                ({ getFieldValue }) => ({
                  validator: (_, value) => getFieldValue('is_enabled') && !value
                    ? Promise.reject(new Error('启用分析时请选择日期列'))
                    : Promise.resolve(),
                }),
              ]}
            >
              <Select allowClear options={columnOptions} style={{ width: 200 }} />
            </Form.Item>
            <Form.Item label="日期格式" name="date_format" extra="留空自动识别 ISO、斜杠和中文日期。">
              <Input placeholder="例如 %Y/%m/%d" style={{ width: 200 }} />
            </Form.Item>
          </Space>

          <Alert
            showIcon
            type={sourceRole === 'workshop_detail' || sourceRole === 'shared_detail' ? 'info' : 'warning'}
            message={sourceRoleHelp[sourceRole]}
            style={{ marginBottom: 20 }}
          />

          <Form.Item label="维度映射（可选）" name="dimensions_json" extra="输入 JSON 对象，键为看板分组名称，值为表头名称；“$sheet_title”会固定取当前工作表标题。">
            <Input.TextArea rows={3} placeholder={'例如 {"车间":"$sheet_title"} 或 {"产线":"生产线"}'} />
          </Form.Item>

          <Card size="small" title="能源指标列" style={{ background: '#fafaf9', marginBottom: 20 }}>
            <Form.List
              name="metrics"
              rules={[
                {
                  validator: async (_, metrics) => {
                    if (form.getFieldValue('is_enabled') && (!metrics || metrics.length === 0)) {
                      throw new Error('启用分析时请至少添加一个能源指标')
                    }
                  },
                },
              ]}
            >
              {(fields, { add, remove }, { errors }) => (
                <>
                  {fields.map((field) => (
                    <div key={field.key} style={{ display: 'grid', gridTemplateColumns: '1fr 1.2fr 1fr .8fr 1fr 1fr auto', gap: 8, alignItems: 'start', marginBottom: 8 }}>
                      <Form.Item name={[field.name, 'metric_key']} rules={[{ required: true, message: '指标名' }]}><Input placeholder="指标名称" /></Form.Item>
                      <Form.Item name={[field.name, 'value_column']} rules={[{ required: true, message: '数值列' }]}><Select placeholder="数值列" options={columnOptions} /></Form.Item>
                      <Form.Item name={[field.name, 'energy_type']} rules={[{ required: true, message: '能源类别' }]}><Input placeholder="如 电力" /></Form.Item>
                      <Form.Item name={[field.name, 'unit']} rules={[{ required: true, message: '单位' }]}><Input placeholder="如 kWh" /></Form.Item>
                      <Form.Item name={[field.name, 'value_semantics']} initialValue="direct"><Select options={[{ value: 'direct', label: '期间消耗' }, { value: 'cumulative', label: '累计表底' }]} /></Form.Item>
                      <Form.Item
                        name={[field.name, 'meter_key_column']}
                        rules={[
                          {
                            validator: async (_, value) => {
                              if (form.getFieldValue(['metrics', field.name, 'value_semantics']) === 'cumulative' && !value) {
                                throw new Error('累计表底需选择计量点列')
                              }
                            },
                          },
                        ]}
                      >
                        <Select allowClear placeholder="累计计量点列" options={columnOptions} />
                      </Form.Item>
                      <Button danger type="text" icon={<DeleteOutlined />} onClick={() => remove(field.name)} aria-label="删除指标" />
                    </div>
                  ))}
                  <Button type="dashed" icon={<PlusOutlined />} onClick={() => add({ value_semantics: 'direct' })}>添加指标</Button>
                  <Form.ErrorList errors={errors} />
                </>
              )}
            </Form.List>
          </Card>

          <Space>
            <Button
              icon={<EyeOutlined />}
              onClick={() => {
                void form.validateFields()
                  .then((values) => submit(values, 'preview'))
                  .catch(() => undefined)
              }}
              loading={previewMutation.isPending}
            >
              预览解析
            </Button>
            <Button type="primary" htmlType="submit" icon={<SaveOutlined />} loading={saveMutation.isPending}>保存并回算</Button>
          </Space>
        </Form>
      </Card>

      {preview && (
        <Card title={`预览结果：${preview.valid_row_count} 行有效，${preview.invalid_row_count} 行异常`} style={{ marginTop: 16 }}>
          <Table
            size="small"
            pagination={false}
            rowKey={(record) => `${record.row_index}-${record.values.metric_key || ''}`}
            dataSource={preview.rows}
            columns={[
              { title: '行号', dataIndex: 'row_index', width: 80 },
              { title: '解析值', dataIndex: 'values', render: (values) => Object.keys(values).length ? JSON.stringify(values) : '—' },
              { title: '错误', dataIndex: 'errors', render: (errors) => errors.length ? <Tag color="red">{errors.join('；')}</Tag> : <Tag color="green">有效</Tag> },
            ]}
          />
        </Card>
      )}
    </main>
  )
}
