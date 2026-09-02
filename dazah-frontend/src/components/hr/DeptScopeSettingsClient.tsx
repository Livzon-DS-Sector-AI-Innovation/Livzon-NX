'use client'

import { useEffect, useState, useCallback, useMemo, useRef } from 'react'
import {
  App, Card, Button, Space, Table, Tag, Typography, Select, Input, Popconfirm, Result,
} from 'antd'
import { SearchOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons'
import { pinyin } from 'pinyin-pro'
import { usePermission } from '@/hooks/usePermission'
import {
  fetchDeptScopes,
  fetchTrainingDepartments,
  fetchCustomTrainingDepartments,
  fetchFeishuMembers,
  type DeptScopeItem,
  type FeishuContactVM,
} from '@/lib/api/client/hr'
import { saveDeptScopeAction, clearDeptScopeAction } from '@/actions/hr'

/** 拼音增强成员：预计算全拼/首字母 */
interface EnrichedMember extends FeishuContactVM {
  py: string
  pyf: string
}

/**
 * 用户可见部门配置（部门级数据隔离管理）。
 *
 * 为指定用户配置可查看的培训部门（规范名）；白名单制，未配置的用户看不到任何部门。
 * 仅 hr:write 管理员可访问本页（路由组件内二次校验）。
 */
export default function DeptScopeSettingsClient() {
  const { has } = usePermission()
  const { message, modal } = App.useApp()
  const [rows, setRows] = useState<DeptScopeItem[]>([])
  const [allDeptOptions, setAllDeptOptions] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [savingIds, setSavingIds] = useState<Set<string>>(new Set())
  const [searchKeyword, setSearchKeyword] = useState('')
  const [searchResults, setSearchResults] = useState<FeishuContactVM[]>([])
  const [searching, setSearching] = useState(false)
  const [localScopes, setLocalScopes] = useState<Record<string, string[]>>({})
  // ref 保存最新全量成员（拼音预计算），避免搜索闭包捕获旧值
  const enrichedRef = useRef<EnrichedMember[]>([])
  const membersLoadedRef = useRef(false)

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [scopes, depts, customDepts] = await Promise.all([
        fetchDeptScopes(),
        fetchTrainingDepartments(),
        fetchCustomTrainingDepartments(),
      ])
      setRows(scopes || [])
      // 培训部门 + 自定义部门并集（去重），作为可选可见部门
      setAllDeptOptions(Array.from(new Set([...(depts || []), ...(customDepts || [])])))
      const map: Record<string, string[]> = {}
      for (const s of scopes || []) map[s.user_id] = s.visible_depts || []
      setLocalScopes(map)
    } catch {
      message.error('加载可见部门配置失败')
    } finally {
      setLoading(false)
    }
  }, [message])

  useEffect(() => {
    queueMicrotask(loadData)
  }, [loadData])

  // 首次搜索时分页拉取全量在职联系人（缓存到 ref），后续内存过滤
  const ensureMembersLoaded = useCallback(async () => {
    if (membersLoadedRef.current) return
    setSearching(true)
    try {
      const first = await fetchFeishuMembers({ page: 1, page_size: 100, status: '1' })
      let all = first?.data || []
      const total = first?.meta?.total || all.length
      if (total > all.length) {
        const pages = Math.ceil(total / 100)
        const rest = await Promise.all(
          Array.from({ length: pages - 1 }, (_, i) =>
            fetchFeishuMembers({ page: i + 2, page_size: 100, status: '1' })
          ),
        )
        all = all.concat(...rest.map((r) => r?.data || []))
      }
      // 拼音预计算（全拼 + 首字母，如 zg 匹配 张）
      enrichedRef.current = (all || []).map((m) => ({
        ...m,
        py: pinyin(m.name || '', { toneType: 'none' }).replace(/\s/g, '').toLowerCase(),
        pyf: pinyin(m.name || '', { pattern: 'first', toneType: 'none' }).replace(/\s/g, '').toLowerCase(),
      }))
      membersLoadedRef.current = true
    } catch {
      enrichedRef.current = []
    } finally {
      setSearching(false)
    }
  }, [])

  // 用户搜索：支持中文包含 / 全拼 / 首字母（如 zg 匹配 张三）、部门拼音
  const handleSearch = useCallback(async (keyword: string) => {
    setSearchKeyword(keyword)
    const kw = (keyword || '').trim().toLowerCase()
    if (!kw) {
      setSearchResults([])
      return
    }
    await ensureMembersLoaded()
    const isAscii = /^[a-z0-9]+$/.test(kw)
    const filtered = enrichedRef.current.filter((m) => {
      const name = m.name || ''
      if (name.toLowerCase().includes(kw)) return true
      if ((m.department || '').toLowerCase().includes(kw)) return true
      if (isAscii && (m.py.includes(kw) || m.pyf.includes(kw))) return true
      // 部门拼音匹配（如 sccj 匹配 生产车间）
      if (isAscii) {
        const deptPy = pinyin(m.department || '', { toneType: 'none' }).replace(/\s/g, '').toLowerCase()
        const deptPyf = pinyin(m.department || '', { pattern: 'first', toneType: 'none' }).replace(/\s/g, '').toLowerCase()
        if (deptPy.includes(kw) || deptPyf.includes(kw)) return true
      }
      return false
    })
    setSearchResults(filtered)
  }, [ensureMembersLoaded])

  // 选择用户加入配置列表（尚未配置的用户默认空配置）
  const handleAddUser = useCallback((member: FeishuContactVM) => {
    if (!member.open_id) {
      message.warning('该联系人缺少 open_id，无法配置')
      return
    }
    if (rows.some((r) => r.user_id === member.open_id)) {
      message.info('该用户已在配置列表中')
      return
    }
    const newRow: DeptScopeItem = {
      user_id: member.open_id,
      user_name: member.name || '',
      user_department: member.department || '',
      visible_depts: [],
      updated_at: null,
    }
    setRows((prev) => [...prev, newRow])
    setLocalScopes((prev) => ({ ...prev, [member.open_id]: [] }))
    setSearchKeyword('')
    setSearchResults([])
  }, [rows, message])

  const handleScopeChange = useCallback((userId: string, value: string[]) => {
    setLocalScopes((prev) => ({ ...prev, [userId]: value }))
  }, [])

  const handleSave = useCallback(async (row: DeptScopeItem) => {
    setSavingIds((prev) => new Set(prev).add(row.user_id))
    try {
      const saved = await saveDeptScopeAction(row.user_id, localScopes[row.user_id] || [], {
        user_name: row.user_name,
        user_department: row.user_department,
      })
      // 同步更新行数据（保存成功后状态应回到"已生效"）
      setRows((prev) => prev.map((r) =>
        r.user_id === row.user_id
          ? { ...r, visible_depts: saved.visible_depts || [], updated_at: new Date().toISOString() }
          : r
      ))
      setLocalScopes((prev) => ({ ...prev, [row.user_id]: saved.visible_depts || [] }))
      message.success(`已保存「${row.user_name}」的可见部门配置`)
    } catch (e) {
      message.error(e instanceof Error ? e.message : '保存失败')
    } finally {
      setSavingIds((prev) => {
        const next = new Set(prev)
        next.delete(row.user_id)
        return next
      })
    }
  }, [localScopes, message])

  // 清除配置：清空可见部门（保留用户行，方便重新配置；该用户回退白名单）
  const handleClear = useCallback(async (row: DeptScopeItem) => {
    setSavingIds((prev) => new Set(prev).add(row.user_id))
    try {
      const saved = await saveDeptScopeAction(row.user_id, [])
      setRows((prev) => prev.map((r) =>
        r.user_id === row.user_id
          ? { ...r, visible_depts: saved.visible_depts || [] }
          : r
      ))
      setLocalScopes((prev) => ({ ...prev, [row.user_id]: [] }))
      message.success(`已清除「${row.user_name}」的可见部门（回退为白名单：看不到任何部门）`)
    } catch (e) {
      message.error(e instanceof Error ? e.message : '清除失败')
    } finally {
      setSavingIds((prev) => {
        const next = new Set(prev)
        next.delete(row.user_id)
        return next
      })
    }
  }, [message])

  // 移除：彻底删除该用户的配置记录（后端软删），从列表消失且刷新后不再出现
  const handleRemove = useCallback(async (row: DeptScopeItem) => {
    setSavingIds((prev) => new Set(prev).add(row.user_id))
    try {
      await clearDeptScopeAction(row.user_id)
      setRows((prev) => prev.filter((r) => r.user_id !== row.user_id))
      setLocalScopes((prev) => {
        const next = { ...prev }
        delete next[row.user_id]
        return next
      })
      message.success(`已彻底移除「${row.user_name}」的配置`)
    } catch (e) {
      message.error(e instanceof Error ? e.message : '移除失败')
    } finally {
      setSavingIds((prev) => {
        const next = new Set(prev)
        next.delete(row.user_id)
        return next
      })
    }
  }, [message])

  const changedMap = useMemo(() => {
    const map: Record<string, boolean> = {}
    for (const row of rows) {
      const original = row.visible_depts || []
      const current = localScopes[row.user_id] || []
      map[row.user_id] = original.join('|') !== current.join('|')
    }
    return map
  }, [rows, localScopes])

  // 注意：权限判断必须放在所有 hooks 之后（用户异步加载时避免 hooks 顺序变化）
  const forbidden = !has('hr:write')

  if (forbidden) {
    return (
      <Result
        status="403"
        title="无权限访问"
        subTitle="只有具备 hr:write 权限的管理员可以配置用户可见部门"
      />
    )
  }

  const columns = [
    {
      title: '用户',
      dataIndex: 'user_name',
      key: 'user_name',
      width: 140,
      render: (_: unknown, row: DeptScopeItem) => (
        <Space orientation="vertical" size={0}>
          <Typography.Text strong>{row.user_name || '-'}</Typography.Text>
          {row.user_department && (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {row.user_department}
            </Typography.Text>
          )}
        </Space>
      ),
    },
    {
      title: '可见部门',
      dataIndex: 'visible_depts',
      key: 'visible_depts',
      render: (_: unknown, row: DeptScopeItem) => (
        <Select
          mode="multiple"
          allowClear
          showSearch
          placeholder="选择该用户可查看的培训部门（留空 = 看不到任何部门）"
          value={localScopes[row.user_id] || []}
          onChange={(v: string[]) => handleScopeChange(row.user_id, v)}
          options={allDeptOptions.map((d) => ({ label: d, value: d }))}
          optionFilterProp="label"
          style={{ width: '100%', maxWidth: 480 }}
        />
      ),
    },
    {
      title: '状态',
      dataIndex: 'updated_at',
      key: 'status',
      width: 110,
      render: (_: unknown, row: DeptScopeItem) => (
        changedMap[row.user_id] ? <Tag color="orange">未保存</Tag> : <Tag color="green">已生效</Tag>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 170,
      render: (_: unknown, row: DeptScopeItem) => (
        <Space>
          <Button
            type="primary"
            size="small"
            loading={savingIds.has(row.user_id)}
            onClick={() => handleSave(row)}
          >
            保存
          </Button>
          <Popconfirm
            title="清除该用户的可见部门配置？"
            description="清空可见部门（用户行保留），该用户回退为白名单：看不到任何部门"
            onConfirm={() => handleClear(row)}
          >
            <Button size="small" disabled={savingIds.has(row.user_id)}>清除</Button>
          </Popconfirm>
          <Popconfirm
            title={`彻底移除「${row.user_name}」的配置？`}
            description="删除该用户的可见部门配置记录，从列表消失且刷新后不再出现"
            onConfirm={() => handleRemove(row)}
          >
            <Button size="small" danger disabled={savingIds.has(row.user_id)}>移除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div className="space-y-4">
      <Card>
        <div className="space-y-3">
          <div>
            <Typography.Title level={5} style={{ marginTop: 0 }}>
              用户可见部门配置
            </Typography.Title>
            <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
              部门级数据隔离（白名单制）：用户<strong>未配置时看不到任何部门</strong>的数据，
              在此为指定用户配置可见部门（培训部门名）后生效；有 hr:write 权限的管理员始终可见全部部门。
              支持提前配置：用户尚未登录过系统也可以直接配置，其首次飞书登录后自动生效。
              留空保存 = 清除配置，该用户回退为看不到任何部门。
            </Typography.Paragraph>
          </div>
          <Space>
            <Input.Search
              placeholder="搜索飞书联系人（姓名/拼音）添加配置"
              value={searchKeyword}
              loading={searching}
              onChange={(e) => handleSearch(e.target.value)}
              onSearch={(v) => handleSearch(v)}
              style={{ width: 280 }}
              enterButton={<SearchOutlined />}
              allowClear
            />
            <Button icon={<ReloadOutlined />} onClick={loadData}>
              刷新
            </Button>
          </Space>
          {searchResults.length > 0 && (
            <Card size="small" style={{ maxHeight: 260, overflow: 'auto' }}>
              <Space orientation="vertical" style={{ width: '100%' }}>
                {searchResults.map((m) => (
                  <Button
                    key={m.open_id}
                    block
                    style={{ textAlign: 'left' }}
                    icon={<PlusOutlined />}
                    onClick={() => handleAddUser(m)}
                  >
                    {m.name}（{m.department || '未知部门'}）
                  </Button>
                ))}
              </Space>
            </Card>
          )}
        </div>
      </Card>

      <Card>
        <Table
          rowKey="user_id"
          loading={loading}
          columns={columns}
          dataSource={rows}
          pagination={false}
          locale={{ emptyText: '暂无配置。搜索上方联系人添加，或由系统自动按用户部门生效。' }}
        />
      </Card>
    </div>
  )
}
