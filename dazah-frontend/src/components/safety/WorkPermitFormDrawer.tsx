'use client'

/**
 * 作业票新建/编辑抽屉：按票种动态渲染票面字段（type_data）、人员证件、
 * 风险辨识勾选与安全措施清单（是/不适用 + 填空项）。
 * 模板数据来自 /safety/work-permits/meta；证件候选取证件管理列表。
 */

import {
  WORK_PERMITS_PAGE_KEY,
} from '@/lib/work-permit-api'

import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Button,
  Checkbox,
  DatePicker,
  Drawer,
  Form,
  Input,
  InputNumber,
  message,
  Select,
  Space,
  Spin,
  Typography,
} from 'antd'

import {
  createWorkPermit,
  getCertificateCategories,
  getWorkCertificates,
  getWorkPermitMeta,
  updateWorkCertificate,
  updateWorkPermit,
  type WorkPermitCreateInput,
} from '@/actions/safety'

type MetaShape = {
  permit_types: { value: string; label: string; no_prefix: string }[]
  level_options: Record<string, { value: string; label: string }[]>
  person_roles: Record<
    string,
    { role: string; label: string; cert?: boolean }[]
  >
  measures: Record<
    string,
    { key: string; text: string; group?: string; fill_keys?: string[] }[]
  >
  type_fields: Record<
    string,
    {
      key: string
      label: string
      type: string
      required?: boolean
      options?: string[]
    }[]
  >
  risk_identification_options: string[]
  gas_types: string[]
}

type PersonInput = {
  role: string
  name: string
  certificate_id?: string | null
  certificate_no?: string | null
  certificate_category?: string | null
}

type CertificateOption = {
  id: string
  person_name: string
  certificate_no: string | null
  certificate_category: string
  status: string
}

export function WorkPermitFormDrawer({
  open,
  onClose,
  onCreated,
  editing,
}: {
  open: boolean
  onClose: () => void
  onCreated?: (draft: Record<string, unknown>) => void
  editing?: {
    id: string
    permit_type: string
    permit_level: string
    apply_department?: string | null
    work_description?: string | null
    work_location?: string | null
    work_unit?: string | null
    planned_start_time?: string | null
    planned_end_time?: string | null
    persons?: PersonInput[]
    risk_identifications?: string[]
    safety_measures?: { key: string; status: string; fills?: Record<string, string> }[]
    type_data?: Record<string, unknown>
    related_legacy_no_text?: string | null
    remark?: string | null
  } | null
}) {
  const [form] = Form.useForm()
  const [meta, setMeta] = useState<MetaShape | null>(null)
  const [permitType, setPermitType] = useState<string | null>(null)
  const [permitLevel, setPermitLevel] = useState<string>('none')
  const [typeData, setTypeData] = useState<Record<string, unknown>>({})
  const [persons, setPersons] = useState<PersonInput[]>([])
  const [risks, setRisks] = useState<string[]>([])
  const [measureState, setMeasureState] = useState<
    Record<string, { status: string; fills: Record<string, string> }>
  >({})
  const [certificates, setCertificates] = useState<CertificateOption[]>([])
  const [categories, setCategories] = useState<{ value: string; label: string }[]>([])
  const [saving, setSaving] = useState(false)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!open) return
    const timer = setTimeout(() => {
    void Promise.all([
      getWorkPermitMeta(WORK_PERMITS_PAGE_KEY),
      getWorkCertificates({ pageKey: WORK_PERMITS_PAGE_KEY, pageSize: 200 }),
      getCertificateCategories(WORK_PERMITS_PAGE_KEY),
    ]).then(([metaRes, certRes, catRes]) => {
      if (metaRes.code === 200 && metaRes.data) setMeta(metaRes.data as never)
      if (certRes.code === 200 && certRes.data) {
        setCertificates(certRes.data.items as never)
      }
      if (catRes.code === 200 && catRes.data) {
        setCategories(catRes.data.categories as never)
      }
      setLoading(false)
    })
    }, 0)
    return () => clearTimeout(timer)
  }, [open])

  // 打开/切换编辑对象时的初始化：渲染期调整派生状态（避免 effect 内同步 setState）
  const [syncKey, setSyncKey] = useState('')
  const syncTarget = open ? (editing?.id ?? 'new') : ''
  if (open && syncTarget !== syncKey) {
    setSyncKey(syncTarget)
    if (editing) {
      setPermitType(editing.permit_type)
      setPermitLevel(editing.permit_level)
      setTypeData(editing.type_data ?? {})
      setPersons(editing.persons ?? [])
      setRisks(editing.risk_identifications ?? [])
      const restored: Record<
        string,
        { status: string; fills: Record<string, string> }
      > = {}
      for (const item of editing.safety_measures ?? []) {
        restored[item.key] = {
          status: item.status,
          fills: item.fills ?? {},
        }
      }
      setMeasureState(restored)
      form.setFieldsValue({
        apply_department: editing.apply_department,
        work_description: editing.work_description,
        work_location: editing.work_location,
        work_unit: editing.work_unit,
        related_legacy_no_text: editing.related_legacy_no_text,
        remark: editing.remark,
      })
    } else {
      setPermitType(null)
      setPermitLevel('none')
      setTypeData({})
      setPersons([])
      setRisks([])
      setMeasureState({})
      form.resetFields()
    }
  }

  const typeFields = useMemo(
    () => (permitType ? (meta?.type_fields?.[permitType] ?? []) : []),
    [meta, permitType]
  )
  const roleOptions = useMemo(
    () => (permitType ? (meta?.person_roles?.[permitType] ?? []) : []),
    [meta, permitType]
  )
  const measures = useMemo(
    () => (permitType ? (meta?.measures?.[permitType] ?? []) : []),
    [meta, permitType]
  )

  const handleCertificatePick = useCallback(
    (index: number, certId: string | undefined) => {
      const cert = certificates.find((item) => item.id === certId)
      setPersons((current) =>
        current.map((person, position) =>
          position === index
            ? {
                ...person,
                certificate_id: cert?.id ?? null,
                certificate_no: cert?.certificate_no ?? null,
                certificate_category: cert?.certificate_category ?? null,
                name: cert?.person_name ?? person.name,
              }
            : person
        )
      )
    },
    [certificates]
  )

  const handleSubmit = useCallback(async () => {
    if (!permitType) {
      message.warning('请选择票种')
      return
    }
    const values = await form.validateFields()
    const safetyMeasures = Object.entries(measureState).map(
      ([key, value]) => ({
        key,
        status: value.status,
        fills: value.fills,
      })
    )
    const payload: WorkPermitCreateInput = {
      permit_type: permitType,
      permit_level: permitLevel,
      apply_department: values.apply_department ?? null,
      work_description: values.work_description ?? null,
      work_location: values.work_location ?? null,
      work_unit: values.work_unit ?? null,
      planned_start_time:
        values.planned_start_time?.toISOString?.() ?? null,
      planned_end_time: values.planned_end_time?.toISOString?.() ?? null,
      persons: persons as unknown as Record<string, unknown>[],
      risk_identifications: risks,
      safety_measures: safetyMeasures as unknown as Record<string, unknown>[],
      type_data: typeData,
      related_legacy_no_text: values.related_legacy_no_text ?? null,
      remark: values.remark ?? null,
    }
    setSaving(true)
    const response = editing
      ? await updateWorkPermit(editing.id, payload)
      : await createWorkPermit(payload)
    setSaving(false)
    if (response.code !== 200) {
      message.error(response.message ?? '保存失败')
      return
    }
    message.success(editing ? '作业票已更新' : '作业票草稿已创建')
    onCreated?.(payload as unknown as Record<string, unknown>)
    onClose()
    form.resetFields()
    // updateWorkCertificate 引入仅为避免未来编辑证件快照时遗漏导入提示
    void updateWorkCertificate
  }, [
    permitType,
    permitLevel,
    form,
    measureState,
    persons,
    risks,
    typeData,
    editing,
    onCreated,
    onClose,
  ])

  return (
    <Drawer
      open={open}
      onClose={onClose}
      size={720}
      destroyOnHidden
      title={editing ? '编辑作业票' : '新建作业票'}
      footer={
        <Space style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <Button onClick={onClose}>取消</Button>
          <Button type="primary" loading={saving} onClick={() => void handleSubmit()}>
            保存草稿
          </Button>
        </Space>
      }
    >
      <Spin spinning={loading}>
        <Form form={form} layout="vertical">
          <Space wrap>
            <Form.Item label="票种" required>
              <Select
                style={{ width: 180 }}
                placeholder="选择票种"
                value={permitType}
                disabled={Boolean(editing)}
                options={(meta?.permit_types ?? []).map((item) => ({
                  value: item.value,
                  label: item.label,
                }))}
                onChange={(value) => {
                  setPermitType(value)
                  setTypeData({})
                  setPersons([])
                  setMeasureState({})
                  const levels = meta?.level_options?.[value] ?? []
                  setPermitLevel(levels[0]?.value ?? 'none')
                }}
              />
            </Form.Item>
            {(meta?.level_options?.[permitType ?? '']?.length ?? 0) > 1 && (
              <Form.Item label="作业级别" required>
                <Select
                  style={{ width: 130 }}
                  value={permitLevel}
                  options={(meta?.level_options?.[permitType ?? ''] ?? []).map(
                    (item) => ({ value: item.value, label: item.label })
                  )}
                  onChange={(value) => setPermitLevel(value)}
                />
              </Form.Item>
            )}
          </Space>
          <Form.Item label="作业内容" name="work_description">
            <Input.TextArea rows={2} placeholder="作业内容概述" />
          </Form.Item>
          <Space wrap>
            <Form.Item label="作业地点" name="work_location">
              <Input placeholder="作业地点" style={{ width: 200 }} />
            </Form.Item>
            <Form.Item label="申请单位" name="apply_department">
              <Input placeholder="申请单位" style={{ width: 160 }} />
            </Form.Item>
            <Form.Item label="作业单位" name="work_unit">
              <Input placeholder="作业单位" style={{ width: 160 }} />
            </Form.Item>
          </Space>
          <Space wrap>
            <Form.Item
              label="实施开始时间"
              name="planned_start_time"
              rules={[{ required: true, message: '请选择开始时间' }]}
            >
              <DatePicker showTime style={{ width: 190 }} />
            </Form.Item>
            <Form.Item
              label="实施结束时间"
              name="planned_end_time"
              rules={[{ required: true, message: '请选择结束时间' }]}
            >
              <DatePicker showTime style={{ width: 190 }} />
            </Form.Item>
          </Space>

          {typeFields.length > 0 && (
            <>
              <Typography.Title level={5}>票面信息</Typography.Title>
              <Space wrap>
                {typeFields.map((field) => (
                  <Form.Item key={field.key} label={field.label} required={field.required}>
                    {field.type === 'multi_select' ? (
                      <Select
                        mode="multiple"
                        style={{ width: 260 }}
                        placeholder={field.label}
                        value={(typeData[field.key] as string[]) ?? []}
                        options={(field.options ?? []).map((option) => ({
                          value: option,
                          label: option,
                        }))}
                        onChange={(value) =>
                          setTypeData((current) => ({
                            ...current,
                            [field.key]: value,
                          }))
                        }
                      />
                    ) : field.type === 'select' ? (
                      <Select
                        style={{ width: 160 }}
                        placeholder={field.label}
                        value={(typeData[field.key] as string) ?? undefined}
                        options={(field.options ?? []).map((option) => ({
                          value: option,
                          label: option,
                        }))}
                        onChange={(value) =>
                          setTypeData((current) => ({
                            ...current,
                            [field.key]: value,
                          }))
                        }
                      />
                    ) : field.type === 'number' ? (
                      <InputNumber
                        style={{ width: 160 }}
                        value={(typeData[field.key] as number) ?? undefined}
                        onChange={(value) =>
                          setTypeData((current) => ({
                            ...current,
                            [field.key]: value,
                          }))
                        }
                      />
                    ) : field.type === 'textarea' ? (
                      <Input.TextArea
                        rows={2}
                        style={{ width: 380 }}
                        value={(typeData[field.key] as string) ?? ''}
                        onChange={(event) =>
                          setTypeData((current) => ({
                            ...current,
                            [field.key]: event.target.value,
                          }))
                        }
                      />
                    ) : (
                      <Input
                        style={{ width: 220 }}
                        value={(typeData[field.key] as string) ?? ''}
                        onChange={(event) =>
                          setTypeData((current) => ({
                            ...current,
                            [field.key]: event.target.value,
                          }))
                        }
                      />
                    )}
                  </Form.Item>
                ))}
              </Space>
            </>
          )}

          {roleOptions.length > 0 && (
            <>
              <Typography.Title level={5}>作业人员与证件</Typography.Title>
              {persons.map((person, index) => (
                <Space key={`${person.role}-${index}`} wrap>
                  <Select
                    style={{ width: 130 }}
                    value={person.role}
                    disabled
                    options={roleOptions.map((role) => ({
                      value: role.role,
                      label: role.label,
                    }))}
                  />
                  <Input
                    style={{ width: 120 }}
                    placeholder="姓名"
                    value={person.name}
                    onChange={(event) =>
                      setPersons((current) =>
                        current.map((item, position) =>
                          position === index
                            ? { ...item, name: event.target.value }
                            : item
                        )
                      )
                    }
                  />
                  <Select
                    style={{ width: 220 }}
                    allowClear
                    placeholder={
                      roleOptions[index]?.cert ? '关联证件（必选建议）' : '关联证件（选填）'
                    }
                    value={person.certificate_id ?? undefined}
                    options={certificates.map((cert) => ({
                      value: cert.id,
                      label: `${cert.person_name} ${
                        categories.find((c) => c.value === cert.certificate_category)
                          ?.label ?? ''
                      } ${cert.certificate_no ?? ''} ${
                        cert.status === 'valid' ? '' : `(${cert.status})`
                      }`,
                    }))}
                    onChange={(value) => handleCertificatePick(index, value)}
                  />
                </Space>
              ))}
              <div>
                <Button
                  size="small"
                  onClick={() =>
                    setPersons((current) => [
                      ...current,
                      { role: roleOptions[current.length]?.role ?? current[0]?.role ?? '', name: '' },
                    ])
                  }
                  disabled={persons.length >= roleOptions.length}
                >
                  添加人员
                </Button>
              </div>
            </>
          )}

          <Typography.Title level={5}>风险辨识结果</Typography.Title>
          <Checkbox.Group
            options={meta?.risk_identification_options ?? []}
            value={risks}
            onChange={(value) => setRisks(value as string[])}
          />

          {measures.length > 0 && (
            <>
              <Typography.Title level={5}>安全措施确认</Typography.Title>
              <Space orientation="vertical" size={8} style={{ display: 'flex' }}>
                {measures.map((measure) => {
                  const state = measureState[measure.key]
                  return (
                    <div key={measure.key}>
                      <Space wrap>
                        <Typography.Text style={{ maxWidth: 480 }} >
                          {measure.text}
                        </Typography.Text>
                        <Button
                          size="small"
                          type={state?.status === 'yes' ? 'primary' : 'default'}
                          onClick={() =>
                            setMeasureState((current) => ({
                              ...current,
                              [measure.key]: {
                                status: current[measure.key]?.status === 'yes'
                                  ? ''
                                  : 'yes',
                                fills: current[measure.key]?.fills ?? {},
                              },
                            }))
                          }
                        >
                          是
                        </Button>
                        <Button
                          size="small"
                          type={state?.status === 'not_applicable' ? 'primary' : 'default'}
                          onClick={() =>
                            setMeasureState((current) => ({
                              ...current,
                              [measure.key]: {
                                status: current[measure.key]?.status === 'not_applicable'
                                  ? ''
                                  : 'not_applicable',
                                fills: current[measure.key]?.fills ?? {},
                              },
                            }))
                          }
                        >
                          不适用
                        </Button>
                      </Space>
                      {(measure.fill_keys?.length ?? 0) > 0 &&
                        state?.status === 'yes' && (
                          <Space wrap style={{ marginTop: 4 }}>
                            {(measure.fill_keys ?? []).map((fillKey) => (
                              <Input
                                key={fillKey}
                                size="small"
                                style={{ width: 160 }}
                                placeholder={fillKey}
                                value={state.fills[fillKey] ?? ''}
                                onChange={(event) =>
                                  setMeasureState((current) => ({
                                    ...current,
                                    [measure.key]: {
                                      status: current[measure.key]?.status ?? 'yes',
                                      fills: {
                                        ...current[measure.key]?.fills,
                                        [fillKey]: event.target.value,
                                      },
                                    },
                                  }))
                                }
                              />
                            ))}
                          </Space>
                        )}
                    </div>
                  )
                })}
              </Space>
            </>
          )}

          <Form.Item
            label="关联的其他特殊作业及安全作业票编号（历史/外部口径）"
            name="related_legacy_no_text"
            style={{ marginTop: 16 }}
          >
            <Input placeholder="如 DH-20260101-001、SX-xxx；平台内票据可在详情页结构化关联" />
          </Form.Item>
          <Form.Item label="备注" name="remark">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Spin>
    </Drawer>
  )
}
