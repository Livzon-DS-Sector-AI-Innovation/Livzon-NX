'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import {
  App, Button, Input, Modal, Popconfirm, Select, Space, Switch, Table, Typography,
} from 'antd'
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { fetchFeishuMembers, type DeptMappingItem } from '@/lib/api/client/hr'
import {
  createTrainingDeptMappingAction,
  updateTrainingDeptMappingAction,
  deleteTrainingDeptMappingAction,
} from '@/actions/hr'

interface Props {
  mappings: DeptMappingItem[]
  trainingDepts: string[]
  loading: boolean
  onChanged: () => Promise<void> | void
}

interface FeishuPersonOption {
  name: string
  department: string
}

interface PersonRow {
  id: string
  name: string
  target: string
  remark: string
  enabled: boolean
}

/**
 * 人员归属覆写（培训部门映射的 person 类型行）。
 *
 * 人员临时调线而飞书部门未更新时，把「姓名 → 台账规范部门」配置在这里，
 * 签到转台账、Excel 导入、手动新增、ESG 同步即按覆写部门落线，
 * 无需改代码。人员正式调线并更新飞书后应停用对应行。
 */
export default function PersonDeptMappingClient({
  mappings = [],
  trainingDepts = [],
  loading = false,
  onChanged,
}: Props) {
  const { message } = App.useApp()

  const personRows: PersonRow[] = mappings
    .filter((m) => m.mapping_type === 'person')
    .map((m) => ({
      id: m.id,
      name: m.source_name,
      target: m.target_name || '',
      remark: m.remark || '',
      enabled: m.enabled,
    }))

  const [feishuOptions, setFeishuOptions] = useState<FeishuPersonOption[]>([])
  const [memberLoading, setMemberLoading] = useState(false)
  const [selectedNames, setSelectedNames] = useState<string[]>([])
  const [targetDept, setTargetDept] = useState('')
  const [remark, setRemark] = useState('')
  const [saving, setSaving] = useState(false)
  const [editing, setEditing] = useState<PersonRow | null>(null)
  const [editTarget, setEditTarget] = useState('')
  const [editRemark, setEditRemark] = useState('')
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const searchMembers = useCallback(async (keyword: string) => {
    setMemberLoading(true)
    try {
      const res = await fetchFeishuMembers({
        keyword: keyword || undefined,
        page: 1,
        page_size: 20,
      })
      const rows = (res.data || []) as Array<{ name?: string; department?: string }>
      setFeishuOptions(
        rows
          .filter((r) => r.name)
          .map((r) => ({ name: r.name as string, department: r.department || '' })),
      )
    } catch {
      setFeishuOptions([])
    } finally {
      setMemberLoading(false)
    }
  }, [])

  useEffect(() => {
    // 初始加载飞书在职联系人选项；加载态同步置位与既有页面口径一致
    // eslint-disable-next-line react-hooks/set-state-in-effect
    searchMembers('')
  }, [searchMembers])

  const handleSearch = (keyword: string) => {
    if (searchTimer.current) clearTimeout(searchTimer.current)
    searchTimer.current = setTimeout(() => {
      void searchMembers(keyword.trim())
    }, 300)
  }

  const handleBatchSave = async () => {
    if (selectedNames.length === 0) {
      message.error('请先选择人员')
      return
    }
    if (!targetDept) {
      message.error('请选择归属部门')
      return
    }
    setSaving(true)
    try {
      const existing = new Set(personRows.map((r) => r.name))
      const fresh = selectedNames.filter((n) => !existing.has(n))
      const skipped = selectedNames.filter((n) => existing.has(n))
      for (const name of fresh) {
        await createTrainingDeptMappingAction({
          source_name: name,
          target_name: targetDept,
          mapping_type: 'person',
          match_level: 'both',
          priority: 10,
          enabled: true,
          remark: remark || null,
        })
      }
      message.success(
        fresh.length
          ? `已配置 ${fresh.length} 名人员的归属部门${skipped.length ? `；${skipped.length} 人已有配置，请在列表中编辑` : ''}`
          : '所选人员均已有归属配置，请在列表中编辑',
      )
      setSelectedNames([])
      setTargetDept('')
      setRemark('')
      await onChanged()
    } catch (e) {
      message.error(e instanceof Error ? e.message : '保存失败，已输入内容保留在表单中')
    } finally {
      setSaving(false)
    }
  }

  const handleToggle = async (row: PersonRow, enabled: boolean) => {
    try {
      await updateTrainingDeptMappingAction(row.id, { enabled })
      message.success(enabled ? '已启用' : '已停用')
      await onChanged()
    } catch (e) {
      message.error(e instanceof Error ? e.message : '操作失败')
    }
  }

  const handleEditSave = async () => {
    if (!editing) return
    if (!editTarget) {
      message.error('请选择归属部门')
      return
    }
    setSaving(true)
    try {
      await updateTrainingDeptMappingAction(editing.id, {
        target_name: editTarget,
        remark: editRemark || null,
      })
      message.success(`已更新「${editing.name}」的归属部门`)
      setEditing(null)
      await onChanged()
    } catch (e) {
      message.error(e instanceof Error ? e.message : '保存失败')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (row: PersonRow) => {
    try {
      await deleteTrainingDeptMappingAction(row.id)
      message.success(`已删除「${row.name}」的人员归属配置`)
      await onChanged()
    } catch (e) {
      message.error(e instanceof Error ? e.message : '删除失败')
    }
  }

  const deptSelectOptions = [...new Set([...trainingDepts, ...personRows.map((r) => r.target), targetDept, editTarget])]
    .filter(Boolean)
    .sort((a, b) => a.localeCompare(b, 'zh'))
    .map((d) => ({ value: d, label: d }))

  const columns: ColumnsType<PersonRow> = [
    { title: '姓名', dataIndex: 'name', width: 140 },
    { title: '归属部门', dataIndex: 'target', width: 180 },
    { title: '备注', dataIndex: 'remark', ellipsis: true },
    {
      title: '启用',
      dataIndex: 'enabled',
      width: 90,
      render: (v: boolean, row: PersonRow) => (
        <Switch size="small" checked={v} onChange={(checked) => handleToggle(row, checked)} />
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 140,
      render: (_: unknown, row: PersonRow) => (
        <Space>
          <Button
            size="small"
            onClick={() => {
              setEditing(row)
              setEditTarget(row.target)
              setEditRemark(row.remark)
            }}
          >
            编辑
          </Button>
          <Popconfirm title={`删除「${row.name}」的人员归属配置？`} onConfirm={() => handleDelete(row)}>
            <Button size="small" danger>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div className="space-y-3">
      <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
        人员临时调线而飞书部门未更新时，在这里把「人员 → 台账部门」配置好，
        签到转台账、Excel 导入、手动新增、ESG 同步都会按配置的部门落线（优先于飞书部门）。
        人员正式调线并更新飞书部门后，请停用或删除对应配置。
      </Typography.Paragraph>

      <div className="flex flex-wrap items-end gap-3">
        <div>
          <Typography.Text strong>人员（可多选）</Typography.Text>
          <Select
            mode="multiple"
            showSearch
            allowClear
            style={{ width: 360 }}
            placeholder="搜索飞书在职人员姓名"
            value={selectedNames}
            loading={memberLoading}
            onSearch={handleSearch}
            onChange={(v) => setSelectedNames((v || []) as string[])}
            options={feishuOptions.map((o) => ({
              value: o.name,
              label: o.department ? `${o.name}（${o.department}）` : o.name,
            }))}
            optionFilterProp="label"
            notFoundContent={memberLoading ? '搜索中…' : '未找到人员'}
          />
        </div>
        <div>
          <Typography.Text strong>归属部门</Typography.Text>
          <Select
            showSearch
            style={{ width: 220 }}
            placeholder="选择台账部门"
            value={targetDept || undefined}
            onChange={(v) => setTargetDept(v || '')}
            options={deptSelectOptions}
            optionFilterProp="label"
          />
        </div>
        <div>
          <Typography.Text strong>备注</Typography.Text>
          <Input
            style={{ width: 220 }}
            placeholder="如：2026-09 调入 DR，飞书未改"
            value={remark}
            maxLength={200}
            onChange={(e) => setRemark(e.target.value)}
          />
        </div>
        <Button type="primary" icon={<PlusOutlined />} loading={saving} onClick={handleBatchSave}>
          批量配置
        </Button>
        <Button
          icon={<ReloadOutlined />}
          onClick={() => {
            void searchMembers('')
            void onChanged()
          }}
        >
          刷新
        </Button>
      </div>

      <Table
        rowKey="id"
        size="small"
        loading={loading}
        columns={columns}
        dataSource={personRows}
        pagination={{ pageSize: 20, showSizeChanger: false }}
        locale={{ emptyText: '暂无人员归属覆写。人员调线后在这里配置，台账即按配置落线。' }}
      />

      <Modal
        title={editing ? `编辑人员归属：${editing.name}` : '编辑人员归属'}
        open={!!editing}
        onCancel={() => setEditing(null)}
        onOk={handleEditSave}
        confirmLoading={saving}
        okText="保存"
        cancelText="取消"
        width={480}
      >
        <div className="space-y-3">
          <div>
            <Typography.Text strong>归属部门</Typography.Text>
            <Select
              showSearch
              style={{ width: '100%', marginTop: 4 }}
              value={editTarget || undefined}
              onChange={(v) => setEditTarget(v || '')}
              options={deptSelectOptions}
              optionFilterProp="label"
            />
          </div>
          <div>
            <Typography.Text strong>备注</Typography.Text>
            <Input
              style={{ marginTop: 4 }}
              value={editRemark}
              maxLength={200}
              onChange={(e) => setEditRemark(e.target.value)}
            />
          </div>
        </div>
      </Modal>
    </div>
  )
}
