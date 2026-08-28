'use client'

import { useEffect, useMemo, useState } from 'react'
import { App, Modal, Select, Input, Button, Space, Spin, Tag, Popconfirm, Table } from 'antd'
import { PlusOutlined, DeleteOutlined, EditOutlined } from '@ant-design/icons'
import { pinyin } from 'pinyin-pro'
import type { TrainingPersonnelItem, TrainingPersonnelConfig, Department } from '@/types/hr'
import { fetchFeishuMembers, fetchTrainingPersonnelConfigs, fetchTrainingDepartments } from '@/lib/api/client/hr'
import { saveTrainingPersonnelConfig, deleteTrainingPersonnelConfig } from '@/actions/hr'
import {
  resolveTrainingDept,
  ensureDeptMappings,
  useDeptMappings,
  getCandidateSourceMap,
  getModalRules,
} from './trainingDept'

interface Props {
  open: boolean
  level: '公司级' | '部门级'
  scopeDept?: string
  onClose: () => void
  onApplied: (personnel: TrainingPersonnelItem[]) => void
}

interface Member {
  name: string
  employee_no?: string
}

function applyModalCuration(rows: string[], dropRows: Set<string>, extraRows: string[]): string[] {
  const out = rows.filter((r) => !dropRows.has(r))
  for (const e of extraRows) if (!out.includes(e)) out.push(e)
  return out
}

/** 拼音搜索：支持中文包含、全拼、首字母（如 zg 匹配 张） */
function matchPinyin(text: string, kw: string): boolean {
  const k = kw.trim().toLowerCase()
  if (!k) return true
  if (text.toLowerCase().includes(k)) return true
  if (!/[a-z]/i.test(k)) return false
  const full = pinyin(text, { toneType: 'none', type: 'array' }).join('')
  if (full.toLowerCase().includes(k)) return true
  const initials = pinyin(text, { pattern: 'first', toneType: 'none', type: 'array' }).join('')
  return initials.toLowerCase().includes(k)
}

function aliasDept(name: string): string {
  // 配置表驱动的合并/归并（special/alias/sub201 由 resolveTrainingDept 命中）
  return resolveTrainingDept(name, undefined, []) || name
}

/** 公司级：一级部门罗列，有子部门的展开为子部门行；应用丢弃/合并/归并规则并去重；
 *  父部门行仅在确有直属人员时保留（如 102车间/201车间 已拆分为子车间，不再显示空父行） */
function buildCompanyRows(
  roots: Department[],
  deptsWithMembers: Set<string>,
  dropDepts: Set<string>,
  noExpandDepts: Set<string>,
): string[] {
  const rows: { name: string; sort: number }[] = []
  const seen = new Set<string>()
  const push = (raw: string, sort: number) => {
    const name = aliasDept(raw)
    if (dropDepts.has(raw) || dropDepts.has(name) || seen.has(name)) return
    seen.add(name)
    rows.push({ name, sort })
  }
  const sortedRoots = [...roots].sort((a, b) => (a.sort_order ?? 9999) - (b.sort_order ?? 9999) || a.name.localeCompare(b.name, 'zh'))
  for (const top of sortedRoots) {
    if (dropDepts.has(top.name)) continue
    const kids = (top.children || []).sort(
      (a, b) => (a.sort_order ?? 9999) - (b.sort_order ?? 9999) || a.name.localeCompare(b.name, 'zh'),
    )
    if (kids.length > 0 && !noExpandDepts.has(top.name)) {
      // 父部门行仅在有直属人员时保留（直属父部门的人员有行可落；与子部门别名重复时自动去重）
      if (deptsWithMembers.has(aliasDept(top.name))) push(top.name, top.sort_order ?? 9999)
      kids.forEach((k) => push(k.name, k.sort_order ?? 9999))
    } else {
      push(top.name, top.sort_order ?? 9999)
    }
  }
  return rows.map((r) => r.name)
}

/** 部门级：与公司级相同的全部门行，但本部门（及其子部门行）置顶，方便先选本部门、偶尔补其他部门 */
function buildDeptRows(
  roots: Department[],
  scopeDept: string,
  deptsWithMembers: Set<string>,
  dropDepts: Set<string>,
  noExpandDepts: Set<string>,
): string[] {
  const rows = buildCompanyRows(roots, deptsWithMembers, dropDepts, noExpandDepts)
  const find = (nodes: Department[]): Department | null => {
    for (const n of nodes) {
      if (n.name === scopeDept) return n
      const hit = find(n.children || [])
      if (hit) return hit
    }
    return null
  }
  const node = find(roots)
  const own = node
    ? [node.name, ...(node.children || []).map((k) => k.name)]
    : [scopeDept]
  const head = own.filter((n) => rows.includes(n))
  const headSet = new Set(head)
  return [...head, ...rows.filter((r) => !headSet.has(r))]
}

export default function TrainingPersonnelConfigModal({ open, level, scopeDept, onClose, onApplied }: Props) {
  const { message } = App.useApp()
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [configs, setConfigs] = useState<TrainingPersonnelConfig[]>([])

  // 部门行 + 各部门在职联系人
  const [deptRows, setDeptRows] = useState<string[]>([])
  const [membersByDept, setMembersByDept] = useState<Record<string, Member[]>>({})
  const [deptFilter, setDeptFilter] = useState('')
  // 自定义部门行（手动添加，保存后进入全局部门来源）
  const [customDeptRows, setCustomDeptRows] = useState<string[]>([])
  const [newDept, setNewDept] = useState('')
  // 弹窗内手动移除的部门行（不持久化，仅影响当前展示）
  const [hiddenRows, setHiddenRows] = useState<string[]>([])

  // 编辑区（点击"新建配置"或"编辑"后显示）
  const [editorVisible, setEditorVisible] = useState(false)
  const [editingConfig, setEditingConfig] = useState<TrainingPersonnelConfig | null>(null)
  const [editName, setEditName] = useState('')
  const [editPersonnel, setEditPersonnel] = useState<TrainingPersonnelItem[]>([])

  // 打开时加载：已有配置 + 部门树 + 全量在职飞书联系人
  const { version: mappingVersion } = useDeptMappings()
  const candidateSource = useMemo(() => getCandidateSourceMap(), [mappingVersion])
  useEffect(() => {
    if (!open) return
    let cancelled = false
    setLoading(true)
    ensureDeptMappings().catch(() => {})
    const dept = level === '部门级' ? scopeDept : undefined
    // 弹窗专属规则（配置表 modal_drop/modal_extra/modal_no_expand）
    const modalRules = getModalRules()

    const loadAllMembers = async (): Promise<Record<string, Member[]>> => {
      const first = await fetchFeishuMembers({ page: 1, page_size: 100, status: '1' })
      const total = first.meta?.total || (first.data || []).length
      const pages = Math.min(Math.ceil(total / 100), 20)
      const restPages = Array.from({ length: pages - 1 }, (_, i) => i + 2)
      const rest = restPages.length
        ? await Promise.all(restPages.map((p) => fetchFeishuMembers({ page: p, page_size: 100, status: '1' })))
        : []
      const all = [...(first.data || []), ...rest.flatMap((r) => r.data || [])]
      const grouped: Record<string, Member[]> = {}
      all.forEach((m) => {
        const raw = m.department || '未设置部门'
        if (modalRules.drop.has(raw)) return // 丢弃的部门不提供候选人
        const d = aliasDept(raw)
        if (!grouped[d]) grouped[d] = []
        grouped[d].push({ name: m.name, employee_no: m.employee_no || undefined })
      })
      return grouped
    }

    Promise.all([
      fetchTrainingPersonnelConfigs({ level, department: dept }).catch(() => ({ data: [] as TrainingPersonnelConfig[] })),
      fetchTrainingDepartments().catch((e) => {
        console.error('加载培训部门列表失败', e)
        return [] as string[]
      }),
      loadAllMembers().catch(() => ({} as Record<string, Member[]>)),
    ])
      .then(([cfgRes, trainingDepts, grouped]) => {
        if (cancelled) return
        // 部门行 = 培训有数据部门 ∪ 有在职联系人的部门，确保所有可配置人员的部门都不缺失
        // IT 不是飞书真实部门，统一显示为「AI创新部」（对应飞书 AI创新部 的在职联系人）
        const renameDept = (n: string) => (n === 'IT' ? 'AI创新部' : n)
        const memberDepts = Object.keys(grouped)
        const allDeptNames = Array.from(new Set([...(trainingDepts as string[]), ...memberDepts].map(renameDept)))
        const roots: Department[] = allDeptNames.map((n) => ({ id: n, name: n }))
        const deptsWithMembers = new Set(memberDepts.map(renameDept))
        setConfigs(cfgRes.data || [])
        setMembersByDept(grouped)
        setDeptRows(
          applyModalCuration(
            level === '部门级' && scopeDept
              ? buildDeptRows(roots, scopeDept, deptsWithMembers, modalRules.drop, modalRules.noExpand)
              : buildCompanyRows(roots, deptsWithMembers, modalRules.drop, modalRules.noExpand),
            modalRules.drop,
            modalRules.extra,
          ),
        )
        setEditorVisible(false)
        setEditingConfig(null)
        setEditName('')
        setEditPersonnel([])
        setDeptFilter('')
        setCustomDeptRows([])
        setNewDept('')
        setHiddenRows([])
      })
      .finally(() => !cancelled && setLoading(false))

    return () => { cancelled = true }
  }, [open, level, scopeDept, mappingVersion])

  // ── 新建 / 编辑 / 删除 ──
  const handleNew = () => {
    setEditingConfig(null)
    setEditName('')
    setEditPersonnel([])
    setEditorVisible(true)
  }

  // 姓名 → {合并后部门, 工号}，用于把旧配置的人员部门重映射到新部门行
  const nameToMember = useMemo(() => {
    const idx: Record<string, { dept: string; employee_no?: string }> = {}
    Object.entries(membersByDept).forEach(([dept, list]) => {
      list.forEach((m) => {
        if (!idx[m.name]) idx[m.name] = { dept, employee_no: m.employee_no }
      })
    })
    return idx
  }, [membersByDept])

  const handleEdit = (cfg: TrainingPersonnelConfig) => {
    setEditingConfig(cfg)
    setEditName(cfg.config_name)
    setEditPersonnel(
      (cfg.personnel || []).map((p) => {
        const m = nameToMember[p.name]
        return m ? { ...p, department: m.dept, employee_number: p.employee_number || m.employee_no } : p
      }),
    )
    setEditorVisible(true)
  }

  const handleDelete = async (cfg: TrainingPersonnelConfig) => {
    try {
      await deleteTrainingPersonnelConfig(cfg.id)
      setConfigs((prev) => prev.filter((c) => c.id !== cfg.id))
      if (editingConfig?.id === cfg.id) {
        setEditingConfig(null)
        setEditName('')
        setEditPersonnel([])
        setEditorVisible(false)
      }
      message.success(`配置「${cfg.config_name}」已删除`)
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '删除失败')
    }
  }

  // ── 保存（按部门行顺序+姓名排序，保证签到表顺序稳定） ──
  const handleSave = async () => {
    if (!editName.trim()) {
      message.warning('请输入配置名称（如 A班 / 仪器组）')
      return
    }
    if (editPersonnel.length === 0) {
      message.warning('请至少选择一名参训人员')
      return
    }
    const rowIndex = new Map(allRows.map((r, i) => [r, i]))
    const sorted = [...editPersonnel].sort(
      (a, b) =>
        (rowIndex.get(a.department || '') ?? 9999) - (rowIndex.get(b.department || '') ?? 9999) ||
        a.name.localeCompare(b.name, 'zh'),
    )
    setSaving(true)
    try {
      // 编辑模式下改名：先删旧再建新
      if (editingConfig && editName.trim() !== editingConfig.config_name) {
        await deleteTrainingPersonnelConfig(editingConfig.id)
      }
      await saveTrainingPersonnelConfig({
        level,
        department: level === '部门级' ? scopeDept || null : null,
        config_name: editName.trim(),
        personnel: sorted as unknown as { [key: string]: unknown }[],
      })
      message.success(`配置「${editName.trim()}」已保存`)
      const dept = level === '部门级' ? scopeDept : undefined
      const res = await fetchTrainingPersonnelConfigs({ level, department: dept })
      setConfigs(res.data || [])
      onApplied(sorted)
      setEditingConfig(null)
      setEditName('')
      setEditPersonnel([])
      setEditorVisible(false)
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '保存失败')
    } finally {
      setSaving(false)
    }
  }

  // 表格行 = 部门行 + 已选人员中出现但不在部门行里的部门（避免编辑旧配置时丢人）
  const extraRows = Array.from(new Set(editPersonnel.map((p) => p.department).filter((d): d is string => !!d && !deptRows.includes(d)))).sort((a, b) => a.localeCompare(b, 'zh'))
  // 防御性去重，避免任何路径产生重复 rowKey（保存排序用），并排除手动移除的行
  const allRows = Array.from(new Set([...deptRows, ...customDeptRows, ...extraRows])).filter((r) => !hiddenRows.includes(r))
  // 展示顺序：自定义部门置顶，确保刚添加的部门立即可见（不被滚动区遮挡）
  const tableRows = Array.from(new Set([...customDeptRows, ...deptRows, ...extraRows])).filter((r) => !hiddenRows.includes(r))
  const visibleRows = deptFilter ? tableRows.filter((r) => matchPinyin(r, deptFilter)) : tableRows

  // 移除部门行：从展示中隐藏并清除该行已选人员
  const handleRemoveRow = (dept: string) => {
    setHiddenRows((prev) => (prev.includes(dept) ? prev : [...prev, dept]))
    setEditPersonnel((prev) => prev.filter((p) => p.department !== dept))
  }

  const handleRowChange = (row: string, names: string[]) => {
    setEditPersonnel((prev) => {
      const others = prev.filter((p) => p.department !== row)
      const prevInRow = prev.filter((p) => p.department === row)
      const memberMap = new Map<string, Member>((membersByDept[candidateSource[row] ?? aliasDept(row)] || []).map((m) => [m.name, m]))
      const next = names.map(
        (n) =>
          prevInRow.find((p) => p.name === n) || {
            name: n,
            employee_number: memberMap.get(n)?.employee_no,
            department: row,
          },
      )
      return [...others, ...next]
    })
  }

  const columns = [
    {
      title: level === '公司级' ? '一级部门' : '部门',
      dataIndex: 'dept',
      width: 170,
      render: (dept: string) => (
        <span className="flex items-center gap-1">
          {dept}
          {!deptRows.includes(dept) && <Tag color="orange" style={{ marginLeft: 6 }}>自定义</Tag>}
          <Popconfirm
            title={`确定移除「${dept}」？该行已选人员也会一并清除。`}
            onConfirm={() => handleRemoveRow(dept)}
            okText="确定"
            cancelText="取消"
          >
            <DeleteOutlined
              style={{ marginLeft: 4, fontSize: 12, color: '#999', cursor: 'pointer' }}
              title="移除该部门行"
            />
          </Popconfirm>
        </span>
      ),
    },
    {
      title: '参训人员',
      dataIndex: 'members',
      render: (_: unknown, record: { dept: string }) => {
        const deptMembers = membersByDept[candidateSource[record.dept] ?? aliasDept(record.dept)] || []
        const hasMembers = deptMembers.length > 0
        return (
          <Select
            mode="tags"
            style={{ width: '100%' }}
            placeholder={hasMembers ? '选择参训人员（可手动输入）' : '手动输入参训人员姓名'}
            value={editPersonnel.filter((p) => p.department === record.dept).map((p) => p.name)}
            onChange={(names: string[]) => handleRowChange(record.dept, names)}
            options={deptMembers.map((m) => ({ value: m.name, label: m.name }))}
            showSearch
            filterOption={(input, option) => matchPinyin(String(option?.value ?? ''), input)}
            notFoundContent={hasMembers ? '无匹配人员，可手动输入' : '该部门无在职联系人，请手动输入姓名'}
            maxTagCount="responsive"
          />
        )
      },
    },
    {
      title: '人数',
      width: 70,
      render: (_: unknown, record: { dept: string }) => (
        <span className="text-sm text-gray-600">{editPersonnel.filter((p) => p.department === record.dept).length}</span>
      ),
    },
  ]

  return (
    <Modal
      title={level === '公司级' ? '配置公司级培训人员（各部门负责人）' : `配置部门级培训人员（${scopeDept || ''}）`}
      open={open}
      onCancel={onClose}
      footer={null}
      width={860}
      destroyOnHidden
      mask={{ closable: false }}
      keyboard={false}
    >
      <Spin spinning={loading}>
        <div className="space-y-4">
          {/* 已有配置列表 */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="font-semibold text-sm">已有班组配置</span>
              <Button size="small" icon={<PlusOutlined />} onClick={handleNew}>新建配置</Button>
            </div>
            {configs.length === 0 ? (
              <p className="text-sm text-gray-400">暂无配置，请点击“新建配置”创建</p>
            ) : (
              <div className="divide-y divide-gray-100 border border-gray-100 rounded">
                {configs.map((cfg) => (
                  <div key={cfg.id} className="flex items-center justify-between px-3 py-2">
                    <div>
                      <Tag color="blue">{cfg.config_name}</Tag>
                      <span className="text-sm text-gray-500">{(cfg.personnel || []).length} 人</span>
                    </div>
                    <Space size={6}>
                      <Button size="small" icon={<EditOutlined />} onClick={() => handleEdit(cfg)}>编辑</Button>
                      <Popconfirm title={`确定删除配置「${cfg.config_name}」？`} onConfirm={() => handleDelete(cfg)}>
                        <Button size="small" danger icon={<DeleteOutlined />} />
                      </Popconfirm>
                    </Space>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* 编辑区：按部门行逐行选人 */}
          {editorVisible && (
            <div className="border-t pt-3">
              <div className="flex items-center justify-between mb-3">
                <span className="text-sm font-semibold">
                  {editingConfig ? `编辑「${editingConfig.config_name}」` : '新建配置'}
                </span>
                <Input
                  placeholder="配置名称（如 A班 / 仪器组）"
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  style={{ width: 260 }}
                />
              </div>
              <p className="text-sm text-gray-500 mb-2">
                按部门逐行选择参训人员（{level === '公司级' ? '罗列一级部门，有子部门的自动展开' : `${scopeDept} 置顶，其他部门也可按需选择`}），避免遗漏部门。
              </p>
              <Input.Search
                placeholder="筛选部门"
                allowClear
                onChange={(e) => setDeptFilter(e.target.value)}
                style={{ width: 220, marginBottom: 8 }}
              />
              <Space style={{ marginBottom: 8 }}>
                <Input
                  placeholder="自定义部门名称"
                  value={newDept}
                  onChange={(e) => setNewDept(e.target.value)}
                  style={{ width: 180 }}
                />
                <Button
                  size="small"
                  icon={<PlusOutlined />}
                  onClick={() => {
                    const d = newDept.trim()
                    if (!d) {
                      message.warning('请输入部门名称')
                      return
                    }
                    if (allRows.includes(d)) {
                      message.warning(`部门「${d}」已存在`)
                      setNewDept('')
                      return
                    }
                    setCustomDeptRows((prev) => [...prev, d])
                    setNewDept('')
                    message.success(`已添加部门「${d}」，可在表格顶部选择参训人员`)
                  }}
                >
                  添加部门
                </Button>
              </Space>
              <Table
                rowKey="dept"
                size="small"
                pagination={false}
                dataSource={visibleRows.map((dept) => ({ dept }))}
                columns={columns}
                scroll={{ y: 380 }}
              />
              <div className="flex items-center gap-3 mt-3">
                <span className="text-sm text-gray-600">已选 {editPersonnel.length} 人</span>
                <Button type="primary" onClick={handleSave} loading={saving}>
                  保存配置
                </Button>
                <Button onClick={() => setEditorVisible(false)}>取消</Button>
              </div>
            </div>
          )}
        </div>
      </Spin>
    </Modal>
  )
}
