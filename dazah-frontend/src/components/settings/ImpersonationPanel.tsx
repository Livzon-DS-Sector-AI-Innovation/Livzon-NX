'use client'

import { getUserErrorMessage } from '@/lib/user-error'
import { useEffect, useState } from 'react'
import { Button, Input, Modal, Select, Table, Tag, Tooltip, Typography } from 'antd'
import { CloseCircleFilled, SearchOutlined } from '@ant-design/icons'
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import { switchWorkspaceIdentity } from '@/components/auth/WorkspaceIdentitySync'
import PlatformNotice from '@/components/shared/PlatformNotice'
import { useSearchFilter } from '@/hooks/useSearchFilter'
import { listImpersonationTargets, startImpersonation, type ImpersonationTarget } from '@/lib/api/client/impersonation'
import { saveImpersonationListState, takeRestoredImpersonationListState } from '@/lib/impersonationListState'
import type { RoleItem } from '@/lib/api/server/admin'

const PAGE_SIZE = 20
const VISIBLE_ROLE_COUNT = 2
type RoleOption = Pick<RoleItem, 'id' | 'name'>

export default function ImpersonationPanel({ roles }: { roles: RoleOption[] }) {
  const [queryClient] = useState(() => new QueryClient())
  return <QueryClientProvider client={queryClient}><ImpersonationTargets roles={roles} /></QueryClientProvider>
}

function ImpersonationTargets({ roles }: { roles: RoleOption[] }) {
  const [keyword, setKeyword] = useState('')
  const [roleId, setRoleId] = useState('')
  const [page, setPage] = useState(1)
  const { inputProps, searchPending, setSearchText } = useSearchFilter(keyword, (value) => {
    setKeyword(value)
    setPage(1)
  })
  const [ready, setReady] = useState(false)
  const [target, setTarget] = useState<ImpersonationTarget>()
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    queueMicrotask(() => {
      if (cancelled) return
      const saved = takeRestoredImpersonationListState()
      if (saved) {
        const roleAvailable = !saved.roleId || roles.some(role => role.id === saved.roleId)
        setKeyword(saved.keyword)
        setSearchText(saved.keyword)
        setRoleId(roleAvailable ? saved.roleId : '')
        setPage(roleAvailable ? saved.page : 1)
      }
      setReady(true)
    })
    return () => {
      cancelled = true
    }
  }, [roles, setSearchText])

  const query = useQuery({
    queryKey: ['settings', 'impersonation-targets', keyword, roleId, page],
    queryFn: ({ signal }) => listImpersonationTargets({
      keyword, role_id: roleId || undefined, offset: (page - 1) * PAGE_SIZE, limit: PAGE_SIZE,
    }, signal),
    enabled: ready && !searchPending,
    retry: false,
  })

  const total = query.data?.total
  if (!searchPending && total !== undefined) {
    const lastPage = Math.max(1, Math.ceil(total / PAGE_SIZE))
    if (page > lastPage) setPage(lastPage)
  }

  async function confirm() {
    if (!target || pending) return
    setPending(true)
    setError('')
    try {
      await switchWorkspaceIdentity('opening', async () => {
        await startImpersonation(target.id)
        saveImpersonationListState({ keyword, roleId, page })
        return '/'
      })
    } catch (failure) {
      setError(getUserErrorMessage(failure instanceof Error ? failure.message : '暂时无法开始模拟', '暂时无法开始模拟'))
      setPending(false)
    }
  }

  return <div className="space-y-4">
    <div className="flex flex-wrap items-center gap-2">
      <Input
        {...inputProps}
        role="searchbox"
        aria-label="搜索姓名、账号或工号"
        placeholder="搜索姓名、账号或工号"
        prefix={<SearchOutlined aria-hidden />}
        allowClear={{ clearIcon: <CloseCircleFilled aria-label="清空搜索" /> }}
        maxLength={100}
        className="max-w-sm"
      />
      <Select<string>
        aria-label="按角色筛选"
        className="w-48 max-w-full"
        value={roleId}
        showSearch={{ optionFilterProp: 'label' }}
        options={[{ value: '', label: '全部角色' }, ...roles.map(role => ({ value: role.id, label: role.name }))]}
        onChange={(value) => {
          setRoleId(value)
          setPage(1)
        }}
      />
    </div>
    {query.isError && !searchPending
      ? <PlatformNotice
        type="error"
        title={query.error.message}
        showRulesLink={false}
        action={<Button disabled={query.isFetching} onClick={() => void query.refetch()}>重试</Button>}
      />
      : <Table<ImpersonationTarget>
        rowKey="id"
        size="small"
        scroll={{ x: 600 }}
        loading={searchPending || query.isFetching}
        locale={{ emptyText: searchPending || query.isPending ? '正在查询用户…' : '暂无可模拟的用户' }}
        dataSource={searchPending ? [] : query.data?.items ?? []}
        pagination={{
          current: page, pageSize: PAGE_SIZE, total: query.data?.total,
          showSizeChanger: false, disabled: searchPending, onChange: setPage,
        }}
        columns={[
          { title: '姓名', dataIndex: 'name' },
          { title: '账号 / 工号', render: (_, user) => user.username || user.employee_no || user.id },
          { title: '部门', dataIndex: 'department', render: (department: string | null) => department || '—' },
          {
            title: '角色',
            key: 'roles',
            render: (_, { roles }) => {
              if (!roles.length) return <Typography.Text type="secondary">未分配角色</Typography.Text>

              const remainingRoles = roles.slice(VISIBLE_ROLE_COUNT)
              return <div className="flex flex-wrap items-center gap-1">
                {roles.slice(0, VISIBLE_ROLE_COUNT).map(role => <Tag key={role.id} className="max-w-full"
                  style={{ marginInlineEnd: 0, whiteSpace: 'normal', overflowWrap: 'anywhere' }}>
                  {role.name}
                </Tag>)}
                {remainingRoles.length > 0 && (
                  <Tooltip title={remainingRoles.map(role => role.name).join('、')} trigger={['hover', 'focus']}>
                    <Button type="text" size="small" onClick={event => event.currentTarget.focus()}>
                      更多（{remainingRoles.length}+）
                    </Button>
                  </Tooltip>
                )}
              </div>
            },
          },
          { title: '操作', render: (_, user) => <Button type="link" aria-label={`模拟登录 ${user.name}`} onClick={() => {
            setError('')
            setTarget(user)
          }}>模拟登录</Button> },
        ]}
      />}
    <Modal
      title="确认模拟登录"
      open={Boolean(target)}
      centered
      onOk={confirm}
      onCancel={() => setTarget(undefined)}
      okText="切换身份"
      cancelText="取消"
      confirmLoading={pending}
      closable={!pending}
      keyboard={!pending}
      mask={{ closable: !pending }}
      cancelButtonProps={{ disabled: pending }}
      destroyOnHidden
    >
      {target && <p>切换到 <strong>{target.name}（{target.username || target.employee_no || target.id}）</strong>，以该用户的权限访问页面和数据。</p>}
      <p>提交、审批、同步等操作会实际生效，审计会记录发起管理员和目标用户。当前浏览器的其他平台标签页也会切换身份。</p>
      <div aria-live="assertive">
        {error && <Typography.Text type="danger">{error}</Typography.Text>}
      </div>
    </Modal>
  </div>
}
