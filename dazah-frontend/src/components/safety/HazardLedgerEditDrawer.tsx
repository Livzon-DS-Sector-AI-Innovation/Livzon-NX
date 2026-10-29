'use client'

import { useState } from 'react'
import { App, Button, Drawer, Input, InputNumber, Select, Space, Typography } from 'antd'
import { SaveOutlined } from '@ant-design/icons'
import { updateHazardIdentification } from '@/actions/safety'
import type { HazardIdentification } from '@/types/safety'
import { RISK_LEVEL_OPTIONS } from '@/types/safety'

const { Text } = Typography

interface Props {
  record: HazardIdentification
  open: boolean
  onClose: () => void
  onSaved: () => void
}

// 平台 LEC 风险等级阈值（D 值 → 等级），与后端 RISK_LEVELS 保持一致
const RISK_THRESHOLDS: Array<{ key: string; min: number }> = [
  { key: 'level_1', min: 320 },
  { key: 'level_2', min: 160 },
  { key: 'level_3', min: 70 },
  { key: 'level_4', min: 0 },
]

const TENSE_OPTIONS = ['过去', '现在', '将来'].map((v) => ({ value: v, label: v }))
const STATE_OPTIONS = ['正常', '异常', '紧急'].map((v) => ({ value: v, label: v }))
const MAJOR_OPTIONS = ['是', '否'].map((v) => ({ value: v, label: v }))

function levelFromD(d: number): string {
  const matched = RISK_THRESHOLDS.find((threshold) => d >= threshold.min)
  return (matched || RISK_THRESHOLDS[RISK_THRESHOLDS.length - 1]).key
}

function levelLabel(key?: string): string | undefined {
  return RISK_LEVEL_OPTIONS.find((option) => option.value === key)?.label
}

interface EditState {
  department: string
  position: string
  hazard_type: string
  production_step: string
  specific_activity: string
  unsafe_behavior: string
  possible_accident: string
  tense: string | undefined
  state: string | undefined
  l_inherent: number | null
  e_inherent: number | null
  c_inherent: number | null
  d_inherent: number | null
  inherent_risk_level: string | undefined
  existing_engineering_controls: string
  existing_management_controls: string
  existing_ppe: string
  existing_emergency_measures: string
  control_level: string | undefined
  responsible_unit: string
  responsible_person: string
  check_frequency: string
  is_major_hazard: string | undefined
  notes: string
}

function buildState(record: HazardIdentification): EditState {
  return {
    department: record.department || '',
    position: record.position || '',
    hazard_type: record.hazard_type || '',
    production_step: record.production_step || '',
    specific_activity: record.specific_activity || '',
    unsafe_behavior: record.unsafe_behavior || '',
    possible_accident: record.possible_accident || '',
    tense: record.tense || undefined,
    state: record.state || undefined,
    l_inherent: record.l_inherent ?? null,
    e_inherent: record.e_inherent ?? null,
    c_inherent: record.c_inherent ?? null,
    d_inherent: record.d_inherent ?? null,
    inherent_risk_level: record.inherent_risk_level,
    existing_engineering_controls: record.existing_engineering_controls || '',
    existing_management_controls: record.existing_management_controls || '',
    existing_ppe: record.existing_ppe || '',
    existing_emergency_measures: record.existing_emergency_measures || '',
    control_level: record.control_level || undefined,
    responsible_unit: record.responsible_unit || '',
    responsible_person: record.responsible_person || '',
    check_frequency: record.check_frequency || '',
    is_major_hazard: record.is_major_hazard || undefined,
    notes: record.notes || '',
  }
}

const sectionTitle = (text: string) => (
  <Text strong style={{ fontSize: 13, display: 'block', marginTop: 8, color: '#5645D4' }}>
    {text}
  </Text>
)

export default function HazardLedgerEditDrawer({ record, open, onClose, onSaved }: Props) {
  const { message } = App.useApp()
  const [draft, setDraft] = useState<EditState>(() => buildState(record))
  const [saving, setSaving] = useState(false)

  const setField = <K extends keyof EditState>(key: K, value: EditState[K]) => {
    setDraft((prev) => ({ ...prev, [key]: value }))
  }

  // L/E/C 任一变化 → 重算 D（E 缺省按 LSR 口径 L*C）并联动建议等级
  const updateLec = (field: 'l_inherent' | 'e_inherent' | 'c_inherent', value: number | null) => {
    setDraft((prev) => {
      const next = { ...prev, [field]: value }
      const { l_inherent: l, e_inherent: e, c_inherent: c } = next
      if (l != null && c != null) {
        const d = e != null ? l * e * c : l * c
        next.d_inherent = Math.round(d * 100) / 100
        next.inherent_risk_level = levelFromD(next.d_inherent)
      }
      return next
    })
  }

  const updateD = (value: number | null) => {
    setDraft((prev) => {
      const next = { ...prev, d_inherent: value }
      if (value != null) {
        next.inherent_risk_level = levelFromD(value)
      }
      return next
    })
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      const payload: Partial<HazardIdentification> = {
        department: draft.department.trim(),
        position: draft.position.trim(),
        hazard_type: draft.hazard_type.trim() || undefined,
        production_step: draft.production_step.trim(),
        specific_activity: draft.specific_activity.trim() || undefined,
        unsafe_behavior: draft.unsafe_behavior.trim() || undefined,
        possible_accident: draft.possible_accident.trim() || undefined,
        tense: draft.tense,
        state: draft.state,
        l_inherent: draft.l_inherent ?? undefined,
        e_inherent: draft.e_inherent ?? undefined,
        c_inherent: draft.c_inherent ?? undefined,
        d_inherent: draft.d_inherent ?? undefined,
        inherent_risk_level: draft.inherent_risk_level,
        inherent_risk_label: levelLabel(draft.inherent_risk_level),
        existing_engineering_controls: draft.existing_engineering_controls.trim() || undefined,
        existing_management_controls: draft.existing_management_controls.trim() || undefined,
        existing_ppe: draft.existing_ppe.trim() || undefined,
        existing_emergency_measures: draft.existing_emergency_measures.trim() || undefined,
        control_level: draft.control_level,
        responsible_unit: draft.responsible_unit.trim() || undefined,
        responsible_person: draft.responsible_person.trim() || undefined,
        check_frequency: draft.check_frequency.trim() || undefined,
        is_major_hazard: draft.is_major_hazard,
        notes: draft.notes.trim() || undefined,
      }
      const res = await updateHazardIdentification(record.id, payload)
      if (res.code === 200) {
        message.success('保存成功')
        onSaved()
        onClose()
      } else {
        message.error(res.message || '保存失败')
      }
    } catch {
      message.error('保存失败，请稍后重试')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Drawer
      title={`编辑危险源辨识记录（${record.hazard_id_no}）`}
      open={open}
      onClose={onClose}
      size={640}
      destroyOnHidden
      footer={
        <Space style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <Button onClick={onClose}>取消</Button>
          <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={handleSave}>
            保存
          </Button>
        </Space>
      }
    >
      <Space direction="vertical" size={4} style={{ width: '100%' }}>
        <Space wrap>
          <Input
            style={{ width: 180 }}
            addonBefore="部门"
            value={draft.department}
            onChange={(e) => setField('department', e.target.value)}
          />
          <Input
            style={{ width: 180 }}
            addonBefore="岗位"
            value={draft.position}
            onChange={(e) => setField('position', e.target.value)}
          />
        </Space>

        {sectionTitle('风险点')}
        <Space wrap>
          <Input
            style={{ width: 180 }}
            addonBefore="类别"
            value={draft.hazard_type}
            onChange={(e) => setField('hazard_type', e.target.value)}
          />
          <Input
            style={{ width: 260 }}
            addonBefore="名称"
            value={draft.production_step}
            onChange={(e) => setField('production_step', e.target.value)}
          />
        </Space>

        {sectionTitle('危险源')}
        <Input
          addonBefore="作业步骤"
          value={draft.specific_activity}
          onChange={(e) => setField('specific_activity', e.target.value)}
        />
        <Input.TextArea
          rows={2}
          placeholder="危险源辨识"
          value={draft.unsafe_behavior}
          onChange={(e) => setField('unsafe_behavior', e.target.value)}
        />

        {sectionTitle('事故类型 · 时态 · 状态')}
        <Space wrap>
          <Input
            style={{ width: 200 }}
            addonBefore="事故类型"
            value={draft.possible_accident}
            onChange={(e) => setField('possible_accident', e.target.value)}
          />
          <Select
            style={{ width: 100 }}
            value={draft.tense}
            onChange={(v) => setField('tense', v)}
            options={TENSE_OPTIONS}
            placeholder="时态"
            allowClear
          />
          <Select
            style={{ width: 100 }}
            value={draft.state}
            onChange={(v) => setField('state', v)}
            options={STATE_OPTIONS}
            placeholder="状态"
            allowClear
          />
        </Space>

        {sectionTitle('安全风险等级评定')}
        <Space wrap>
          <InputNumber
            style={{ width: 110 }}
            addonBefore="L"
            min={0}
            value={draft.l_inherent}
            onChange={(v) => updateLec('l_inherent', v)}
          />
          <InputNumber
            style={{ width: 110 }}
            addonBefore="E"
            min={0}
            value={draft.e_inherent}
            onChange={(v) => updateLec('e_inherent', v)}
          />
          <InputNumber
            style={{ width: 110 }}
            addonBefore="C"
            min={0}
            value={draft.c_inherent}
            onChange={(v) => updateLec('c_inherent', v)}
          />
          <InputNumber
            style={{ width: 110 }}
            addonBefore="D"
            min={0}
            value={draft.d_inherent}
            onChange={updateD}
          />
        </Space>
        <Space wrap>
          <Select
            style={{ width: 200 }}
            value={draft.inherent_risk_level}
            onChange={(v) => setField('inherent_risk_level', v)}
            options={RISK_LEVEL_OPTIONS.map((option) => ({
              value: option.value,
              label: option.label,
            }))}
            placeholder="风险等级"
          />
          <Text type="secondary" style={{ fontSize: 12 }}>
            L/E/C 变更时自动重算 D 并按阈值建议等级（≥320 一级 / ≥160 二级 / ≥70 三级 / 其余四级），可手动改
          </Text>
        </Space>

        {sectionTitle('风险管控措施')}
        <Input.TextArea
          rows={2}
          placeholder="工程措施"
          value={draft.existing_engineering_controls}
          onChange={(e) => setField('existing_engineering_controls', e.target.value)}
        />
        <Input.TextArea
          rows={2}
          placeholder="管理措施"
          value={draft.existing_management_controls}
          onChange={(e) => setField('existing_management_controls', e.target.value)}
        />
        <Space wrap>
          <Input.TextArea
            style={{ width: 280 }}
            rows={2}
            placeholder="个体防护"
            value={draft.existing_ppe}
            onChange={(e) => setField('existing_ppe', e.target.value)}
          />
          <Input.TextArea
            style={{ width: 280 }}
            rows={2}
            placeholder="应急措施"
            value={draft.existing_emergency_measures}
            onChange={(e) => setField('existing_emergency_measures', e.target.value)}
          />
        </Space>

        {sectionTitle('管控主体')}
        <Space wrap>
          <Select
            style={{ width: 140 }}
            value={draft.control_level}
            onChange={(v) => setField('control_level', v)}
            options={['公司级', '部门级', '车间级', '班组级', '岗位级'].map((v) => ({
              value: v,
              label: v,
            }))}
            placeholder="管控层级"
            allowClear
          />
          <Input
            style={{ width: 150 }}
            addonBefore="责任单位"
            value={draft.responsible_unit}
            onChange={(e) => setField('responsible_unit', e.target.value)}
          />
          <Input
            style={{ width: 150 }}
            addonBefore="责任人员"
            value={draft.responsible_person}
            onChange={(e) => setField('responsible_person', e.target.value)}
          />
        </Space>

        {sectionTitle('检查安排')}
        <Space wrap>
          <Input
            style={{ width: 180 }}
            addonBefore="检查频次"
            value={draft.check_frequency}
            onChange={(e) => setField('check_frequency', e.target.value)}
          />
          <Select
            style={{ width: 160 }}
            value={draft.is_major_hazard}
            onChange={(v) => setField('is_major_hazard', v)}
            options={MAJOR_OPTIONS}
            placeholder="是否重要危险源"
            allowClear
          />
        </Space>

        {sectionTitle('备注')}
        <Input.TextArea
          rows={3}
          value={draft.notes}
          onChange={(e) => setField('notes', e.target.value)}
        />
      </Space>
    </Drawer>
  )
}
