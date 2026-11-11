'use client'

/** 应急预案 AI 工作台 — 生成/导入向导。

四步：基本信息 → 场景要素 → 组织机构确认 → 确认生成；
import 模式只有两步：基本信息 → 上传 docx。
组织机构按级别给默认组结构，并用同级别最近一份预案预填人名；
留空的姓名生成后显示“（待定）”，可后续在工作台对话中补全。
 */

import { useEffect, useMemo, useState } from 'react'
import {
  App,
  Button,
  DatePicker,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Steps,
  Tag,
  Upload,
} from 'antd'
import { ThunderboltOutlined, UploadOutlined } from '@ant-design/icons'
import dayjs, { type Dayjs } from 'dayjs'

import {
  createEmergencyPlan,
  fetchEmergencyPlanAiOptions,
  importEmergencyPlanDocx,
  submitEmergencyPlanGenerate,
  type EmergencyPlanAiOptionsData,
  type EmergencyPlanDocumentData,
  type EmergencyPlanGenerateParams,
} from '@/actions/safety'

const LEVEL_LABELS: Record<string, string> = {
  company: '公司级',
  workshop: '车间级',
}

export interface GeneratedOrgGroup {
  name: string
  leader: string
  members: string
  duties: string
}

export interface WizardOrganization {
  commander: string
  deputyCommanders: string[]
  groups: GeneratedOrgGroup[]
}

interface Props {
  open: boolean
  mode: 'generate' | 'import'
  onClose: () => void
  onCreated: (planId: string) => void
}

interface BasicValues {
  name: string
  level: 'company' | 'workshop'
  accidentType?: string
  drillDate?: Dayjs | null
  archiveDepartment?: string
}

interface SceneValues {
  location?: string
  locationDetail?: string
  substances?: string[]
  participatingDepartments?: string[]
  startTime?: string
  scenarioRequirements?: string
}

function defaultGroups(level: string): GeneratedOrgGroup[] {
  return level === 'company'
    ? [
        { name: '应急处置组', leader: '', members: '', duties: '' },
        { name: '工程抢险组', leader: '', members: '', duties: '' },
        { name: '医疗救护组', leader: '', members: '', duties: '' },
        { name: '环境监测组', leader: '', members: '', duties: '' },
        { name: '警戒疏散组', leader: '', members: '', duties: '' },
        { name: '应急资源保障组', leader: '', members: '', duties: '' },
        { name: '公共关系与后勤组', leader: '', members: '', duties: '' },
      ]
    : [
        { name: '应急处置组', leader: '', members: '', duties: '' },
        { name: '警戒疏散组', leader: '', members: '', duties: '' },
        { name: '医疗救护组', leader: '', members: '', duties: '' },
        { name: '设备抢险组', leader: '', members: '', duties: '' },
        { name: '通讯联络组', leader: '', members: '', duties: '' },
      ]
}

const ACCIDENT_FALLBACK = [
  { value: 'fire', label: '火灾' },
  { value: 'leak', label: '泄漏' },
  { value: 'leak_fire', label: '泄漏火灾' },
  { value: 'explosion', label: '爆炸' },
  { value: 'poisoning', label: '中毒窒息' },
  { value: 'electric', label: '触电' },
]

export default function EmergencyPlanGenerateModal({
  open,
  mode,
  onClose,
  onCreated,
}: Props) {
  const [step, setStep] = useState(0)
  const [options, setOptions] = useState<EmergencyPlanAiOptionsData | null>(null)
  const [basic, setBasic] = useState<BasicValues>({
    name: '',
    level: 'company',
  })
  const [scene, setScene] = useState<SceneValues>({
    startTime: '14:00',
    substances: [],
    participatingDepartments: [],
  })
  const [organization, setOrganization] = useState<WizardOrganization>(() => ({
    commander: '',
    deputyCommanders: [],
    groups: defaultGroups('company'),
  }))
  const { message } = App.useApp()
  const [file, setFile] = useState<File | null>(null)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    let cancelled = false
    fetchEmergencyPlanAiOptions().then((res) => {
      if (cancelled) return
      if (res.code === 200 && res.data) {
        setOptions(res.data)
        const recent = res.data.recent_organization ?? null
        if (recent) {
          setOrganization((prev) => ({
            commander: prev.commander || recent.commander || '',
            deputyCommanders:
              prev.deputyCommanders.length > 0
                ? prev.deputyCommanders
                : (recent.deputy_commanders ?? []),
            groups: prev.groups.map((group) => {
              const found = (recent.groups ?? []).find(
                (item) => item.name === group.name
              )
              return found ? { ...group, leader: found.leader || '' } : group
            }),
          }))
        }
      }
    })
    return () => {
      cancelled = true
    }
  }, [])

  const accidentOptions = useMemo(
    () =>
      (options?.accident_types ?? ACCIDENT_FALLBACK).map((item) => ({
        value: item.value,
        label: item.label,
      })),
    [options]
  )
  const substanceOptions = useMemo(
    () =>
      (options?.chemicals ?? []).map((item) => ({
        value: item.name,
        label: `${item.name}${item.has_msds ? '（有MSDS）' : '（无MSDS）'}`,
      })),
    [options]
  )
  const locationOptions = useMemo(
    () => (options?.buildings ?? []).map((item) => ({ value: item.name })),
    [options]
  )

  const suggestedName = useMemo(() => {
    if (mode === 'import') return basic.name
    const accident =
      accidentOptions.find((item) => item.value === basic.accidentType)?.label ??
      ''
    const location = scene.location ?? ''
    const substances = (scene.substances ?? []).join('')
    return `${location}${substances}${accident}综合应急演练方案`.replace(
      /^\s+/,
      ''
    )
  }, [mode, basic, scene, accidentOptions])

  const switchLevel = (level: 'company' | 'workshop') => {
    setBasic((prev) => ({ ...prev, level }))
    const defaults = defaultGroups(level)
    setOrganization((prev) => {
      const kept = prev.groups.filter((group) =>
        defaults.some((item) => item.name === group.name)
      )
      const merged = defaults.map(
        (item) => kept.find((group) => group.name === item.name) ?? item
      )
      return { ...prev, groups: merged }
    })
  }

  const buildParams = (): EmergencyPlanGenerateParams => ({
    level: basic.level,
    accident_type: basic.accidentType ?? 'other',
    location: scene.location ?? '',
    location_detail: scene.locationDetail ?? '',
    substances: (scene.substances ?? []).map((name) => ({ name })),
    company: options?.default_company ?? '',
    drill_date: basic.drillDate ? basic.drillDate.format('YYYY-MM-DD') : null,
    start_time: scene.startTime ?? '14:00',
    archive_department: basic.archiveDepartment ?? '',
    participating_departments: scene.participatingDepartments ?? [],
    scenario_requirements: scene.scenarioRequirements ?? '',
    organization: {
      commander: organization.commander,
      commander_duties: '',
      deputy_commanders: organization.deputyCommanders,
      deputy_duties: '',
      groups: organization.groups,
    },
    workshop_organization: null,
  })

  const handleSubmit = async () => {
    if (mode === 'import' && !file) {
      message.warning('请选择要导入的 .docx 文档')
      return
    }
    setSubmitting(true)
    try {
      const created = await createEmergencyPlan({
        name: basic.name,
        plan_type: 'comprehensive',
        version: 'V1.0',
        status: 'active',
        department: basic.archiveDepartment ?? '',
        remark: '',
      })
      if (created.code !== 200 || !created.data?.id) {
        message.error(created.message || '创建预案失败')
        return
      }
      const planId = created.data.id as string
      if (mode === 'import') {
        const imported = await importEmergencyPlanDocx(planId, file as File)
        if (imported.code !== 200) {
          message.error(imported.message || '导入失败')
          return
        }
        onCreated(planId)
        return
      }
      const submitted = await submitEmergencyPlanGenerate(planId, buildParams())
      if (submitted.code !== 200 && submitted.code !== 202) {
        message.error(submitted.message || '提交生成任务失败')
        return
      }
      message.success('已提交 AI 生成任务，正在进入工作台…')
      onCreated(planId)
    } finally {
      setSubmitting(false)
    }
  }

  const steps =
    mode === 'generate'
      ? ['基本信息', '场景要素', '组织机构', '确认生成']
      : ['基本信息', '导入文档']

  return (
    <Modal
      title={
        <Space>
          <ThunderboltOutlined style={{ color: '#7b5ce0' }} />
          {mode === 'generate' ? 'AI 生成应急预案' : '导入预案文档'}
        </Space>
      }
      open={open}
      onCancel={onClose}
      width={720}
      destroyOnHidden
      footer={
        <Space>
          <Button onClick={onClose}>取消</Button>
          {step > 0 && (
            <Button onClick={() => setStep((prev) => prev - 1)}>上一步</Button>
          )}
          {step < steps.length - 1 && (
            <Button type="primary" onClick={() => setStep((prev) => prev + 1)}>
              下一步
            </Button>
          )}
          {step === steps.length - 1 && (
            <Button
              type="primary"
              loading={submitting}
              onClick={handleSubmit}
              disabled={mode === 'generate' && !basic.name}
            >
              {mode === 'generate' ? '创建并开始 AI 生成' : '创建并导入'}
            </Button>
          )}
        </Space>
      }
    >
      <Steps
        size="small"
        current={step}
        items={steps.map((title) => ({ title }))}
        style={{ marginBottom: 24 }}
      />
      {step === 0 && (
        <Form layout="vertical">
          <Form.Item label="级别" required>
            <Select
              value={basic.level}
              onChange={(value) => switchLevel(value)}
              options={[
                { value: 'company', label: '公司级' },
                { value: 'workshop', label: '车间级' },
              ]}
            />
          </Form.Item>
          <Form.Item
            label="预案名称"
            required
            extra={
              mode === 'generate' && suggestedName
                ? `建议名称：${suggestedName}（可点右侧按钮采用）`
                : undefined
            }
          >
            <Space.Compact style={{ width: '100%' }}>
              <Input
                value={basic.name}
                placeholder="如：危险品库乙醇火灾事故综合应急演练方案"
                onChange={(event) =>
                  setBasic((prev) => ({ ...prev, name: event.target.value }))
                }
              />
              {mode === 'generate' && suggestedName && (
                <Button onClick={() => setBasic((prev) => ({ ...prev, name: suggestedName }))}>
                  采用建议
                </Button>
              )}
            </Space.Compact>
          </Form.Item>
          {mode === 'generate' && (
            <>
              <Form.Item label="事故类型" required>
                <Select
                  value={basic.accidentType}
                  placeholder="请选择事故类型"
                  options={accidentOptions}
                  onChange={(value) =>
                    setBasic((prev) => ({ ...prev, accidentType: value }))
                  }
                />
              </Form.Item>
              <Form.Item label="演练日期">
                <DatePicker
                  style={{ width: '100%' }}
                  value={basic.drillDate}
                  onChange={(value) =>
                    setBasic((prev) => ({ ...prev, drillDate: value }))
                  }
                />
              </Form.Item>
            </>
          )}
          <Form.Item label="建档部门">
            <Input
              value={basic.archiveDepartment}
              placeholder="如：消保队"
              onChange={(event) =>
                setBasic((prev) => ({
                  ...prev,
                  archiveDepartment: event.target.value,
                }))
              }
            />
          </Form.Item>
        </Form>
      )}
      {step === 1 && mode === 'generate' && (
        <Form layout="vertical">
          <Form.Item label="事故场所" required>
            <AutoCompleteFree
              value={scene.location ?? ''}
              options={locationOptions}
              onChange={(value) => setScene((prev) => ({ ...prev, location: value }))}
              placeholder="如：危险品库（可从厂区建筑选择或直接输入）"
            />
          </Form.Item>
          <Form.Item label="具体位置（可选）">
            <Input
              value={scene.locationDetail}
              placeholder="如：5号库乙醇储存区"
              onChange={(event) =>
                setScene((prev) => ({ ...prev, locationDetail: event.target.value }))
              }
            />
          </Form.Item>
          <Form.Item
            label="涉及物质"
            extra="已关联 MSDS 的物质，AI 将直接引用其理化数据，数值不会凭空编写"
          >
            <Select
              mode="multiple"
              value={scene.substances}
              options={substanceOptions}
              placeholder="选择危化品档案中的物质"
              onChange={(value) => setScene((prev) => ({ ...prev, substances: value }))}
            />
          </Form.Item>
          <Form.Item label="参演部门">
            <Select
              mode="tags"
              value={scene.participatingDepartments}
              placeholder="输入后回车，如：仓储部、消保队"
              onChange={(value) =>
                setScene((prev) => ({
                  ...prev,
                  participatingDepartments: value,
                }))
              }
            />
          </Form.Item>
          <Form.Item label="情景起始时刻">
            <Input
              value={scene.startTime}
              placeholder="14:00"
              onChange={(event) =>
                setScene((prev) => ({ ...prev, startTime: event.target.value }))
              }
            />
          </Form.Item>
          <Form.Item label="补充要求（可选）">
            <Input.TextArea
              rows={3}
              value={scene.scenarioRequirements}
              placeholder="对情景脚本的特殊要求，如：需包含夜间响应环节"
              onChange={(event) =>
                setScene((prev) => ({
                  ...prev,
                  scenarioRequirements: event.target.value,
                }))
              }
            />
          </Form.Item>
        </Form>
      )}
      {step === 2 && mode === 'generate' && (
        <div>
          <p style={{ color: 'rgba(0,0,0,0.55)', marginTop: 0 }}>
            人员姓名可通过下方填写，也可留空生成后在工作台对话中补充（正文以
            “（待定）”占位）。已按同级别最近一份预案预填。
          </p>
          <Form layout="vertical">
            <Form.Item label="总指挥">
              <Input
                value={organization.commander}
                onChange={(event) =>
                  setOrganization((prev) => ({
                    ...prev,
                    commander: event.target.value,
                  }))
                }
              />
            </Form.Item>
            <Form.Item label="副总指挥（顿号分隔）">
              <Input
                value={organization.deputyCommanders.join('、')}
                onChange={(event) =>
                  setOrganization((prev) => ({
                    ...prev,
                    deputyCommanders: event.target.value
                      .split(/[、,，]/)
                      .map((item) => item.trim())
                      .filter(Boolean),
                  }))
                }
              />
            </Form.Item>
            {organization.groups.map((group, index) => (
              <Space.Compact
                key={group.name}
                style={{ display: 'flex', marginBottom: 8 }}
              >
                <Input style={{ width: 160 }} value={group.name} disabled />
                <Input
                  placeholder="组长（可空）"
                  value={group.leader}
                  onChange={(event) =>
                    setOrganization((prev) => ({
                      ...prev,
                      groups: prev.groups.map((item, itemIndex) =>
                        itemIndex === index
                          ? { ...item, leader: event.target.value }
                          : item
                      ),
                    }))
                  }
                />
                <Input
                  placeholder="成员（可空）"
                  value={group.members}
                  onChange={(event) =>
                    setOrganization((prev) => ({
                      ...prev,
                      groups: prev.groups.map((item, itemIndex) =>
                        itemIndex === index
                          ? { ...item, members: event.target.value }
                          : item
                      ),
                    }))
                  }
                />
              </Space.Compact>
            ))}
          </Form>
        </div>
      )}
      {step === steps.length - 1 && (
        <div>
          {mode === 'import' ? (
            <Form layout="vertical">
              <Form.Item
                label="预案文档（.docx）"
                required
                extra="系统按公司 12 章模板解析章节、组织机构与封面信息；识别出的错误将由 AI 审核自动修正"
              >
                <Upload
                  accept=".docx"
                  maxCount={1}
                  beforeUpload={(uploadFile) => {
                    setFile(uploadFile as File)
                    return false
                  }}
                  onRemove={() => setFile(null)}
                >
                  <Button icon={<UploadOutlined />}>选择文件</Button>
                </Upload>
              </Form.Item>
            </Form>
          ) : (
            <div>
              <Space direction="vertical" size={8} style={{ width: '100%' }}>
                <div>
                  <Tag color="purple">{LEVEL_LABELS[basic.level]}</Tag>
                  <Tag>{basic.accidentType ? accidentOptions.find((item) => item.value === basic.accidentType)?.label : '未选'}</Tag>
                  {(scene.substances ?? []).map((name) => (
                    <Tag key={name}>{name}</Tag>
                  ))}
                </div>
                <div>名称：{basic.name || suggestedName || '（未填写）'}</div>
                <div>
                  场所：{scene.location || '（未填写）'}
                  {scene.locationDetail ? `（${scene.locationDetail}）` : ''}
                </div>
                <div>
                  演练日期：
                  {basic.drillDate
                    ? dayjs(basic.drillDate).format('YYYY-MM-DD')
                    : '（未填）'}
                  ，情景起始 {scene.startTime}
                </div>
                <div>
                  组织机构：总指挥 {organization.commander || '（待定）'}
                  ，{organization.groups.length} 个小组
                </div>
                <div style={{ color: 'rgba(0,0,0,0.55)' }}>
                  点击“创建并开始 AI 生成”后，将创建预案记录并后台生成初稿
                  （约 2-4 分钟），完成后自动进入工作台。
                </div>
              </Space>
            </div>
          )}
        </div>
      )}
    </Modal>
  )
}

/** antd AutoComplete 在测试桩中难以渲染，用 Input + datalist 简化实现。 */
function AutoCompleteFree({
  value,
  options,
  onChange,
  placeholder,
}: {
  value: string
  options: { value: string }[]
  onChange: (value: string) => void
  placeholder?: string
}) {
  return (
    <>
      <Input
        value={value}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
      />
      {options.length > 0 && (
        <datalist id="emergency-plan-locations">
          {options.slice(0, 50).map((item) => (
            <option key={item.value} value={item.value} />
          ))}
        </datalist>
      )}
    </>
  )
}

export type { EmergencyPlanDocumentData }
