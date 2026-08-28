'use client'

import { useEffect, useMemo, useState, useCallback } from 'react'
import { App, Button, Card, Checkbox, DatePicker, Empty, Input, Modal, Space, Spin, Table, Tag } from 'antd'
import {
  DownloadOutlined,
  ImportOutlined,
  PlusOutlined,
  DeleteOutlined,
  EditOutlined,
  SearchOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import { HR_DISPLAY_DATE_FORMAT, fmtTrainingDatetime } from '@/lib/dayjs-config'
import {
  fetchTrainingDepartments,
  fetchEmployeeTrainingMembers,
  fetchEmployeeTrainingRecords,
  type EmployeeTrainingMemberItem,
  type EmployeeTrainingRecordItem,
} from '@/lib/api/client/hr'
import {
  importFeishuMembers,
  addEmployeeTrainingMember,
  removeEmployeeTrainingMember,
  updateEmployeeTrainingMember,
} from '@/actions/hr'

export default function EmployeeTrainingListClient() {
  const { message, modal } = App.useApp()
  // 部门
  const [deptTabs, setDeptTabs] = useState<{ key: string; label: string }[]>([])
  const [selectedDept, setSelectedDept] = useState<string>('')
  // 左面板：部门人员
  const [members, setMembers] = useState<EmployeeTrainingMemberItem[]>([])
  const [membersLoading, setMembersLoading] = useState(false)
  const [nameFilter, setNameFilter] = useState<string>('')
  const [selectedMember, setSelectedMember] = useState<EmployeeTrainingMemberItem | null>(null)
  const [addName, setAddName] = useState('')
  const [importing, setImporting] = useState(false)
  const [adding, setAdding] = useState(false)
  // 勾选批量删除
  const [checkedIds, setCheckedIds] = useState<Set<string>>(new Set())
  const [batchRemoving, setBatchRemoving] = useState(false)
  // 编辑改名
  const [editingMember, setEditingMember] = useState<EmployeeTrainingMemberItem | null>(null)
  const [editName, setEditName] = useState('')
  const [editing, setEditing] = useState(false)
  // 右面板：个人培训清单
  const [records, setRecords] = useState<EmployeeTrainingRecordItem[]>([])
  const [recordsLoading, setRecordsLoading] = useState(false)
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs | null, dayjs.Dayjs | null] | null>(null)
  const [exporting, setExporting] = useState(false)
  const [exportingZip, setExportingZip] = useState(false)

  // 部门列表与培训台账页面完全一致（数据驱动，随台账部门增加/删除）
  const loadDepartments = useCallback(async () => {
    try {
      const departments = await fetchTrainingDepartments()
      const tabs = departments.map((d) => ({ key: d, label: d }))
      setDeptTabs(tabs)
      setSelectedDept((prev) => prev || tabs[0]?.key || '')
    } catch {
      message.error('加载部门列表失败')
    }
  }, [message])

  useEffect(() => {
    queueMicrotask(loadDepartments)
  }, [loadDepartments])

  // 选中部门 → 自动加载该部门人员
  const loadMembers = useCallback(async (department: string) => {
    if (!department) return
    setMembersLoading(true)
    try {
      setMembers(await fetchEmployeeTrainingMembers(department))
    } catch (e) {
      message.error((e instanceof Error ? e.message : '') || '加载部门人员失败')
    } finally {
      setMembersLoading(false)
    }
  }, [message])

  useEffect(() => {
    queueMicrotask(() => {
      setSelectedMember(null)
      setRecords([])
      setCheckedIds(new Set())
      void loadMembers(selectedDept)
    })
  }, [selectedDept, loadMembers])

  // 左面板姓名筛选（前端本地过滤）
  const filteredMembers = useMemo(() => {
    if (!nameFilter.trim()) return members
    return members.filter((m) => m.name.includes(nameFilter.trim()))
  }, [members, nameFilter])

  // 点击人员 → 右面板加载该人培训记录
  const loadRecords = useCallback(
    async (member: EmployeeTrainingMemberItem) => {
      setRecordsLoading(true)
      try {
        const dateFrom = dateRange?.[0]?.format('YYYY-MM-DD')
        const dateTo = dateRange?.[1]?.format('YYYY-MM-DD')
        setRecords(await fetchEmployeeTrainingRecords(member.name, dateFrom, dateTo))
      } catch (e) {
        message.error((e instanceof Error ? e.message : '') || '加载培训记录失败')
      } finally {
        setRecordsLoading(false)
      }
    },
    [dateRange, message]
  )

  const handleSelectMember = (member: EmployeeTrainingMemberItem) => {
    setSelectedMember(member)
    loadRecords(member)
  }

  // 时间段变化时刷新当前人员记录
  useEffect(() => {
    if (selectedMember) queueMicrotask(() => void loadRecords(selectedMember))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dateRange])

  // 勾选（仅配置表人员可勾选，auto 无 id）
  const toggleChecked = (id: string | null | undefined) => {
    if (!id) return
    setCheckedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  // 导出下载（fetch-blob 封装，右面板单导出与顶部 zip 导出共用；
  // 不设置 a.download，使用后端 Content-Disposition 中的文件名）
  const downloadUrl = useCallback(async (url: string) => {
    const res = await fetch(url, { cache: 'no-store' })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error((err instanceof Error ? err.message : '') || err.detail || '导出失败')
    }
    const blob = await res.blob()
    const objectUrl = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = objectUrl
    a.click()
    window.URL.revokeObjectURL(objectUrl)
  }, [])

  // 右面板：导出当前人员清单
  const handleExportOne = async () => {
    if (!selectedMember) return
    setExporting(true)
    try {
      const sp = new URLSearchParams({ department: selectedDept, name: selectedMember.name })
      if (dateRange?.[0]) sp.set('date_from', dateRange[0].format('YYYY-MM-DD'))
      if (dateRange?.[1]) sp.set('date_to', dateRange[1].format('YYYY-MM-DD'))
      await downloadUrl(
        `/api/v1/hr/training/employee-training-list/export?${sp.toString()}`
      )
      message.success('导出成功')
    } catch (e) {
      message.error((e instanceof Error ? e.message : '') || '导出失败')
    } finally {
      setExporting(false)
    }
  }

  // 顶部：一键导出当前部门全部人员 zip
  const handleExportAll = async () => {
    if (!selectedDept) {
      message.warning('请先选择部门')
      return
    }
    setExportingZip(true)
    try {
      const sp = new URLSearchParams({ department: selectedDept })
      if (dateRange?.[0]) sp.set('date_from', dateRange[0].format('YYYY-MM-DD'))
      if (dateRange?.[1]) sp.set('date_to', dateRange[1].format('YYYY-MM-DD'))
      await downloadUrl(
        `/api/v1/hr/training/employee-training-list/export?${sp.toString()}`
      )
      message.success('导出成功')
    } catch (e) {
      message.error((e instanceof Error ? e.message : '') || '导出失败')
    } finally {
      setExportingZip(false)
    }
  }

  // 左面板：拉取飞书人员（自动匹配到当前部门，公用账号自动排除）
  const handleImportDept = async () => {
    if (!selectedDept) return
    setImporting(true)
    try {
      const res = await importFeishuMembers(selectedDept)
      message.success(res.message || '导入完成')
      await loadMembers(selectedDept)
    } catch (e) {
      message.error((e instanceof Error ? e.message : '') || '导入失败')
    } finally {
      setImporting(false)
    }
  }

  // 左面板：手动添加人员（可添加非飞书联系人，如离职人员）
  const handleAddMember = async () => {
    if (!selectedDept) return
    const name = addName.trim()
    if (!name) {
      message.warning('请输入姓名')
      return
    }
    setAdding(true)
    try {
      await addEmployeeTrainingMember(selectedDept, name)
      message.success('人员已添加')
      setAddName('')
      await loadMembers(selectedDept)
    } catch (e) {
      message.error((e instanceof Error ? e.message : '') || '添加失败')
    } finally {
      setAdding(false)
    }
  }

  // 每行删除
  const handleRemoveOne = (member: EmployeeTrainingMemberItem) => {
    if (!member.id) return
    modal.confirm({
      title: '移除人员',
      content: `确认将「${member.name}」从 ${selectedDept} 的培训清单中移除？`,
      okText: '移除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        try {
          await removeEmployeeTrainingMember(member.id!)
          message.success('已移除')
          if (selectedMember?.name === member.name) setSelectedMember(null)
          await loadMembers(selectedDept)
        } catch (e) {
          message.error((e instanceof Error ? e.message : '') || '移除失败')
        }
      },
    })
  }

  // 底部批量删除
  const handleBatchRemove = () => {
    const ids = [...checkedIds]
    if (ids.length === 0) return
    modal.confirm({
      title: '批量移除人员',
      content: `确认移除已勾选的 ${ids.length} 名人员？`,
      okText: '移除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        setBatchRemoving(true)
        try {
          for (const id of ids) {
            await removeEmployeeTrainingMember(id)
          }
          message.success(`已移除 ${ids.length} 名人员`)
          setCheckedIds(new Set())
          await loadMembers(selectedDept)
        } catch (e) {
          message.error((e instanceof Error ? e.message : '') || '批量移除失败')
        } finally {
          setBatchRemoving(false)
        }
      },
    })
  }

  // 清除当前选中人员的培训清单（双重确认弹窗）
  const handleClearSelected = () => {
    if (!selectedMember?.id) return
    const name = selectedMember.name
    modal.confirm({
      title: '清除员工培训清单',
      content: `即将清除「${name}」的员工培训清单（该人员将从本部门清单中移除），确定继续？`,
      okText: '继续',
      cancelText: '取消',
      onOk: () => {
        modal.confirm({
          title: '再次确认',
          content: `「${name}」的员工培训清单将被清除，此操作不可恢复，确认清除？`,
          okText: '确认清除',
          okButtonProps: { danger: true },
          cancelText: '取消',
          onOk: async () => {
            try {
              await removeEmployeeTrainingMember(selectedMember.id!)
              message.success('已清除培训清单')
              setSelectedMember(null)
              await loadMembers(selectedDept)
            } catch (e) {
              message.error((e instanceof Error ? e.message : '') || '清除失败')
            }
          },
        })
      },
    })
  }

  // 编辑改名
  const openEdit = (member: EmployeeTrainingMemberItem) => {
    setEditingMember(member)
    setEditName(member.name)
  }

  const handleEditSave = async () => {
    const name = editName.trim()
    if (!editingMember?.id || !name) {
      message.warning('请输入姓名')
      return
    }
    setEditing(true)
    try {
      await updateEmployeeTrainingMember(editingMember.id, name)
      message.success('姓名已更新')
      setEditingMember(null)
      if (selectedMember?.name === editingMember.name) {
        setSelectedMember({ ...selectedMember, name })
      }
      await loadMembers(selectedDept)
    } catch (e) {
      message.error((e instanceof Error ? e.message : '') || '编辑失败')
    } finally {
      setEditing(false)
    }
  }

  // 右面板表格列（与 HR-QD-01 模板正文一致）
  const recordColumns = [
    { title: '序号', key: 'index', width: 60, render: (_: unknown, __: unknown, i: number) => i + 1 },
    {
      title: '培训时间',
      dataIndex: 'training_datetime',
      key: 'training_datetime',
      render: (v: string | null, r: EmployeeTrainingRecordItem) =>
        v ? fmtTrainingDatetime(v) : (r.training_date ? dayjs(String(r.training_date)).format(HR_DISPLAY_DATE_FORMAT) : '-'),
    },
    { title: '培训内容', dataIndex: 'training_content', key: 'training_content', render: (v: string | null) => v || '-' },
    { title: '考核结果', dataIndex: 'personal_score', key: 'personal_score', width: 100, render: (v: string | null) => v || '-' },
    { title: '备注', dataIndex: 'remarks', key: 'remarks', render: (v: string | null) => v || '-' },
  ]

  return (
    <div className="space-y-4">
      {/* 顶部：部门区（flex-wrap 分行罗列，随培训台账部门变化） */}
      <Card size="small" title="部门（与培训台账一致）">
        <div className="flex flex-wrap items-center gap-2">
          {deptTabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setSelectedDept(tab.key)}
              className={`px-4 py-2 rounded-lg border text-sm transition-all ${
                selectedDept === tab.key
                  ? 'border-blue-500 bg-blue-50 text-blue-600'
                  : 'border-gray-200 bg-white text-gray-600 hover:border-blue-300'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <div className="mt-3 flex items-center gap-2">
          <Button
            type="primary"
            icon={<DownloadOutlined />}
            loading={exportingZip}
            disabled={!selectedDept}
            onClick={handleExportAll}
          >
            一键导出全部（zip）
          </Button>
          <span className="text-xs text-gray-500">
            导出当前部门全部人员的培训清单（按时间段筛选时仅导出该时间段内记录）
          </span>
        </div>
      </Card>

      {/* 主体：左右分栏 */}
      <div className="flex items-start gap-4">
        {/* 左面板：部门人员 */}
        <Card
          size="small"
          title={`部门人员${selectedDept ? ` — ${selectedDept}` : ''}`}
          className="w-[360px] shrink-0"
          styles={{ body: { display: 'flex', flexDirection: 'column', gap: 12, maxHeight: 640 } }}
        >
          <div className="flex gap-2">
            <Input
              allowClear
              placeholder="姓名筛选"
              prefix={<SearchOutlined />}
              value={nameFilter}
              onChange={(e) => setNameFilter(e.target.value)}
            />
          </div>

          <div className="flex-1 overflow-y-auto border rounded">
            {membersLoading ? (
              <div className="flex justify-center py-10">
                <Spin />
              </div>
            ) : filteredMembers.length === 0 ? (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={selectedDept ? '暂无人员，请添加或拉取飞书人员' : '请选择部门'}
                className="py-8"
              />
            ) : (
              <ul className="divide-y">
                {filteredMembers.map((m) => {
                  const active = selectedMember?.name === m.name
                  return (
                    <li
                      key={m.id || `auto-${m.name}`}
                      onClick={() => handleSelectMember(m)}
                      className={`cursor-pointer px-2 py-2 transition-colors ${
                        active
                          ? 'bg-blue-50 border-l-[3px] border-blue-500'
                          : 'border-l-[3px] border-transparent hover:bg-gray-50'
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        {m.id ? (
                          <Checkbox
                            checked={checkedIds.has(m.id)}
                            onClick={(e) => e.stopPropagation()}
                            onChange={() => toggleChecked(m.id)}
                          />
                        ) : (
                          <span className="w-4" />
                        )}
                        <span className="flex-1 text-sm font-medium text-gray-800 truncate">
                          {m.name}
                        </span>
                        {m.source === 'auto' ? (
                          <Tag color="green" style={{ marginInlineEnd: 0 }}>新员工</Tag>
                        ) : (
                          <Space size={2}>
                            <Button
                              type="text"
                              size="small"
                              icon={<EditOutlined />}
                              title="编辑姓名"
                              onClick={(e) => {
                                e.stopPropagation()
                                openEdit(m)
                              }}
                            />
                            <Button
                              type="text"
                              size="small"
                              danger
                              icon={<DeleteOutlined />}
                              title="移除"
                              onClick={(e) => {
                                e.stopPropagation()
                                handleRemoveOne(m)
                              }}
                            />
                          </Space>
                        )}
                      </div>
                    </li>
                  )
                })}
              </ul>
            )}
          </div>

          <div className="flex gap-2">
            <Input
              placeholder="姓名（可添加离职人员）"
              value={addName}
              onChange={(e) => setAddName(e.target.value)}
              onPressEnter={handleAddMember}
            />
            <Button icon={<PlusOutlined />} loading={adding} onClick={handleAddMember}>
              添加
            </Button>
          </div>

          <div className="flex flex-wrap gap-2">
            <Button
              icon={<ImportOutlined />}
              loading={importing}
              disabled={!selectedDept}
              onClick={handleImportDept}
            >
              拉取飞书人员
            </Button>
            <Button
              danger
              icon={<DeleteOutlined />}
              disabled={checkedIds.size === 0}
              loading={batchRemoving}
              onClick={handleBatchRemove}
            >
              批量删除（{checkedIds.size}）
            </Button>
          </div>

          <div className="text-xs text-gray-500">
            说明：「新员工」标记为自动合并（按员工档案所属部门），无需手动维护；离职人员不在飞书联系人中，请手动添加；公用账号已自动排除。点击人员姓名查看右侧培训清单。
          </div>
        </Card>

        {/* 右面板：个人培训清单（与 HR-QD-01 模板正文一致） */}
        <Card
          size="small"
          title={`个人培训清单${selectedMember ? ` — ${selectedMember.name}` : ''}`}
          className="flex-1 min-w-0"
          extra={
            selectedMember && (
              <Space>
                <DatePicker.RangePicker
                  value={dateRange}
                  onChange={(v) =>
                    setDateRange(v as [dayjs.Dayjs | null, dayjs.Dayjs | null] | null)
                  }
                />
                <Button
                  type="primary"
                  icon={<DownloadOutlined />}
                  loading={exporting}
                  onClick={handleExportOne}
                >
                  导出清单
                </Button>
                <Button
                  danger
                  disabled={!selectedMember.id}
                  onClick={handleClearSelected}
                  title="清除当前人员的培训清单（双重确认）"
                >
                  清除
                </Button>
              </Space>
            )
          }
        >
          {selectedMember ? (
            <Table
              rowKey={(r, i) => `${r.training_datetime || ''}-${r.training_content || ''}-${i ?? ''}`}
              columns={recordColumns}
              dataSource={records}
              loading={recordsLoading}
              size="middle"
              pagination={{ pageSize: 20 }}
              locale={{
                emptyText: (
                  <Empty
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                    description="暂无培训记录（可按时间段筛选）"
                  />
                ),
              }}
            />
          ) : (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="请点击左侧人员姓名查看培训清单"
              className="py-16"
            />
          )}
        </Card>
      </div>

      {/* 编辑姓名弹窗 */}
      <Modal
        title="编辑人员姓名"
        open={!!editingMember}
        onCancel={() => setEditingMember(null)}
        onOk={handleEditSave}
        confirmLoading={editing}
        okText="保存"
        cancelText="取消"
        width={360}
      >
        <Input
          value={editName}
          onChange={(e) => setEditName(e.target.value)}
          placeholder="输入新姓名"
          onPressEnter={handleEditSave}
          autoFocus
        />
      </Modal>
    </div>
  )
}
