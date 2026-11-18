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
import dayjs from 'dayjs'

import { usePagePermissions } from '@/hooks/usePagePermissions'
import {
  createWorkPermit,
  getApproverConfigs,
  getCertificateCategories,
  getWorkCertificates,
  getWorkPermitMeta,
  submitWorkPermit,
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
  nodes: Record<
    string,
    { key: string; name: string; kind: string; levels: string[] | null }[]
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
  external?: boolean
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
  // 审批人指派（与聊天流第⑥步/详情页提交 Modal 同口径）：
  // assignments 为覆盖值，留空回退默认审批人配置（后端 submit 同规则）
  const [approverDefaults, setApproverDefaults] = useState<Record<string, string>>({})
  const [assignments, setAssignments] = useState<Record<string, string | null>>({})
  const [userOptions, setUserOptions] = useState<{ value: string; label: string }[]>([])
  const permissions = usePagePermissions(WORK_PERMITS_PAGE_KEY)

  const searchUsers = useCallback(async (keyword: string) => {
    const params = new URLSearchParams({ limit: '50' })
    if (keyword.trim()) params.set('keyword', keyword)
    const response = await fetch(`/api/v1/identity/personnel?${params}`)
    if (response.ok) {
      const json = await response.json()
      setUserOptions(
        ((json.data?.items ?? []) as Record<string, unknown>[]).map((u) => ({
          value: String(u.id),
          label: `${String(u.name)} - ${String(u.department || '未知部门')}`,
        })),
      )
    }
  }, [])

  useEffect(() => {
    if (!open) return
    const timer = setTimeout(() => {
    void Promise.all([
      getWorkPermitMeta(WORK_PERMITS_PAGE_KEY),
      getWorkCertificates({ pageKey: WORK_PERMITS_PAGE_KEY, pageSize: 200 }),
      getCertificateCategories(WORK_PERMITS_PAGE_KEY),
      getApproverConfigs(WORK_PERMITS_PAGE_KEY),
      searchUsers(''),
    ]).then(([metaRes, certRes, catRes, configRes]) => {
      if (metaRes.code === 200 && metaRes.data) setMeta(metaRes.data as never)
      if (certRes.code === 200 && certRes.data) {
        setCertificates(certRes.data.items as never)
      }
      if (catRes.code === 200 && catRes.data) {
        setCategories(catRes.data.categories as never)
      }
      if (configRes.code === 200 && configRes.data) {
        const map: Record<string, string> = {}
        for (const item of configRes.data.items) {
          if (!item.approver_user_id) continue
          map[`${item.permit_type}:${item.node_key}`] = item.approver_user_id
        }
        setApproverDefaults(map)
      }
      setLoading(false)
    })
    }, 0)
    return () => clearTimeout(timer)
  }, [open, searchUsers])

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
        planned_start_time: editing.planned_start_time
          ? dayjs(editing.planned_start_time)
          : undefined,
        planned_end_time: editing.planned_end_time
          ? dayjs(editing.planned_end_time)
          : undefined,
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
    setAssignments({})
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
  // 当前级别真实激活的审批节点（与聊天流第⑥步/提交 Modal 同口径）
  const activeApproveNodes = useMemo(
    () =>
      (permitType ? (meta?.nodes?.[permitType] ?? []) : []).filter(
        (node) =>
          node.kind === 'approve' &&
          (node.levels === null || node.levels.includes(permitLevel))
      ),
    [meta, permitType, permitLevel]
  )
  const missingApproverNodes = useMemo(
    () =>
      activeApproveNodes.filter(
        (node) =>
          !assignments[node.key] && !approverDefaults[`${permitType}:${node.key}`]
      ),
    [activeApproveNodes, assignments, approverDefaults, permitType]
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

  const handleSubmit = useCallback(
    async (submitAfterSave: boolean) => {
      if (!permitType) {
        message.warning('请选择票种')
        return
      }
      if (submitAfterSave && missingApproverNodes.length > 0) {
        message.warning(
          `以下审批节点未指派且无默认配置：${missingApproverNodes
            .map((node) => node.name)
            .join('、')}`
        )
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
      if (response.code !== 200) {
        setSaving(false)
        message.error(response.message ?? '保存失败')
        return
      }
      const permitId = String(
        (response.data as unknown as { id?: string })?.id ?? editing?.id ?? ''
      )
      if (submitAfterSave && permitId) {
        const assignmentsPayload = activeApproveNodes.map((node) => ({
          node_key: node.key,
          approver_user_id: assignments[node.key] ?? null,
        }))
        const submitRes = await submitWorkPermit(permitId, assignmentsPayload)
        setSaving(false)
        if (submitRes.code !== 200) {
          // 草稿已保存，仅提交失败（如证件强校验拦截）：留在弹窗让用户修正
          message.error(submitRes.message ?? '提交审批失败（草稿已保存）')
          return
        }
        message.success('作业票已保存并提交审批')
      } else {
        setSaving(false)
        message.success(editing ? '作业票已更新' : '作业票草稿已创建')
      }
      onCreated?.(payload as unknown as Record<string, unknown>)
      onClose()
      form.resetFields()
      // updateWorkCertificate 引入仅为避免未来编辑证件快照时遗漏导入提示
      void updateWorkCertificate
    },
    [
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
      activeApproveNodes,
      assignments,
      missingApproverNodes,
    ]
  )

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
          <Button loading={saving} onClick={() => void handleSubmit(false)}>
            保存草稿
          </Button>
          {permissions.canOperate && (
            <Button
              type="primary"
              loading={saving}
              onClick={() => void handleSubmit(true)}
            >
              保存并提交审批
            </Button>
          )}
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
              <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 8 }}>
                作业人/吊装作业人等岗位可添加多条（多选）；名单没有的外部人员勾选「外部人员」手工录入。
              </Typography.Text>
              {persons.map((person, index) => {
                const roleOption = roleOptions.find((role) => role.role === person.role)
                return (
                  <div key={`${person.role}-${index}`} style={{ marginBottom: 8 }}>
                    <Space wrap>
                      <Select
                        style={{ width: 150 }}
                        value={person.role || undefined}
                        placeholder="选择岗位"
                        options={roleOptions.map((role) => ({
                          value: role.role,
                          label: role.label + (role.cert ? '（需持证）' : ''),
                        }))}
                        onChange={(value) =>
                          setPersons((current) =>
                            current.map((item, position) =>
                              position === index
                                ? { ...item, role: value }
                                : item
                            )
                          )
                        }
                      />
                      <Input
                        style={{ width: 110 }}
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
                      <Checkbox
                        checked={Boolean(person.external)}
                        onChange={(event) =>
                          setPersons((current) =>
                            current.map((item, position) =>
                              position === index
                                ? {
                                    ...item,
                                    external: event.target.checked || undefined,
                                    certificate_id: event.target.checked
                                      ? null
                                      : item.certificate_id,
                                    certificate_category: event.target.checked
                                      ? null
                                      : item.certificate_category,
                                  }
                                : item
                            )
                          )
                        }
                      >
                        外部人员
                      </Checkbox>
                      {person.external ? (
                        <Input
                          style={{ width: 200 }}
                          placeholder="证件号（外部人员手输）"
                          value={person.certificate_no ?? ''}
                          onChange={(event) =>
                            setPersons((current) =>
                              current.map((item, position) =>
                                position === index
                                  ? { ...item, certificate_no: event.target.value }
                                  : item
                              )
                            )
                          }
                        />
                      ) : (
                        <Select
                          style={{ width: 220 }}
                          allowClear
                          placeholder={
                            roleOption?.cert ? '关联证件（必选建议）' : '关联证件（选填）'
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
                      )}
                      <Button
                        size="small"
                        type="text"
                        danger
                        onClick={() =>
                          setPersons((current) =>
                            current.filter((_, position) => position !== index)
                          )
                        }
                      >
                        删除
                      </Button>
                    </Space>
                  </div>
                )
              })}
              <div>
                <Button
                  size="small"
                  onClick={() =>
                    setPersons((current) => [
                      ...current,
                      { role: roleOptions[current.length]?.role ?? roleOptions[0]?.role ?? '', name: '' },
                    ])
                  }
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

          {activeApproveNodes.length > 0 && permissions.canOperate && (
            <>
              <Typography.Title level={5}>审批人指派</Typography.Title>
              {missingApproverNodes.length > 0 && (
                <Typography.Text
                  type="warning"
                  style={{ display: 'block', marginBottom: 8 }}
                >
                  以下节点未指派且无默认配置，提交前需指派：
                  {missingApproverNodes.map((node) => node.name).join('、')}
                </Typography.Text>
              )}
              {activeApproveNodes.map((node) => {
                const defaultValue = approverDefaults[`${permitType}:${node.key}`]
                const defaultValueLabel =
                  userOptions.find((option) => option.value === defaultValue)?.label ??
                  defaultValue
                return (
                  <Space key={node.key} wrap style={{ marginBottom: 8 }}>
                    <Typography.Text style={{ width: 180, display: 'inline-block' }}>
                      {node.name}
                    </Typography.Text>
                    <Select
                      style={{ width: 240 }}
                      showSearch
                      allowClear
                      filterOption={false}
                      placeholder={
                        defaultValueLabel
                          ? `默认：${defaultValueLabel}（可改）`
                          : '搜索并指派审批人'
                      }
                      value={assignments[node.key] ?? undefined}
                      options={userOptions}
                      onSearch={(keyword) => void searchUsers(keyword)}
                      onFocus={() => {
                        if (userOptions.length === 0) void searchUsers('')
                      }}
                      onChange={(value) =>
                        setAssignments((current) => ({
                          ...current,
                          [node.key]: (value as string) ?? null,
                        }))
                      }
                    />
                  </Space>
                )
              })}
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
