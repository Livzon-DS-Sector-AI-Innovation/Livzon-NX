'use client'

import { useMemo, useState } from 'react'
import Link from 'next/link'
import { Badge, Button, Drawer, Empty, Spin, Tag } from 'antd'
import { CheckSquareOutlined, ReloadOutlined } from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import dayjs from 'dayjs'
import { fetchMyTodos, getTodoSources } from '@/lib/api/myTodos'
import type { ModuleMenu } from '@/lib/menu-config'
import type { User } from '@/types/user'
import PlatformNotice from '@/components/shared/PlatformNotice'
import { isSystemAdministrator } from '@/lib/administrator-role'

export function MyTodos({ user, modules, ready = true }: { user: User; modules: ModuleMenu[]; ready?: boolean }) {
  const systemAdmin = isSystemAdministrator(user)
  const [open, setOpen] = useState(false)
  const sources = useMemo(() => getTodoSources(user, modules), [user, modules])
  const query = useQuery({
    queryKey: ['my-todos', user.id, user.grant_version, sources],
    queryFn: ({ signal }) => fetchMyTodos(sources, signal),
    staleTime: 30_000, refetchInterval: open ? 60_000 : false, retry: false,
  })
  const groups = query.isError ? [] : query.data || []
  const total = groups.reduce((sum, group) => sum + group.total, 0)
  const errors = groups.filter((group) => group.error)
  return <>
    <Badge count={errors.length || query.isError ? undefined : total} overflowCount={99} size="small">
      <Button type="text" disabled={!ready} icon={<CheckSquareOutlined />} onClick={() => { setOpen(true); void query.refetch() }} aria-label="我的待办">
        我的待办
      </Button>
    </Badge>
    <Drawer title="我的待办" open={open} onClose={() => setOpen(false)} size={520} styles={{ wrapper: { maxWidth: '100vw' } }}
      extra={<Button icon={<ReloadOutlined />} loading={query.isFetching} onClick={() => void query.refetch()}>刷新</Button>}>
      <div className="space-y-4">
        {query.isPending ? <div className="py-8 text-center"><Spin aria-label="正在读取待办" /></div> : <>
          {(query.isError || errors.length > 0) && <PlatformNotice type="warning" title="部分待办读取失败，当前数量不完整，请刷新重试。"
            description={errors.map((group) => `${group.source.label}：${group.error}`).join('；') || '请求失败，请重试。'} />}
          {sources.length === 0 ? <Empty description={systemAdmin ? '暂无系统设置待办' : '当前账号暂无已接入的待办处理权限'} /> : !query.isError && errors.length === 0 && total === 0 ? <Empty description="当前没有需要处理的待办" /> : null}
          {groups.filter((group) => !group.error && group.total > 0).map((group) => <section key={group.source.key} className="rounded-[var(--rounded-lg)] bg-[var(--color-surface)] p-4">
            <div className="flex items-start justify-between gap-3 mb-3">
              <h3 className="text-sm font-medium">{group.source.label} <Tag>{group.total} 项</Tag></h3>
              <Link href={group.source.path} onClick={() => setOpen(false)} className="shrink-0 text-[var(--color-primary)]">查看全部</Link>
            </div>
            <ul className="space-y-3">{group.items.map((item) => <li key={item.id}>
              <Link href={group.source.path} onClick={() => setOpen(false)} className="block rounded-[var(--rounded-sm)] focus-visible:outline-2 focus-visible:outline-[var(--color-primary)]">
                <span className="block text-sm">{item.title}</span>
                <span className="text-xs text-[var(--color-steel)]">{item.detail}</span>
                {item.due_date && <span className="block text-xs mt-1">计划／截止日期：{item.due_date}
                  {dayjs(item.due_date).isBefore(dayjs(), 'day') && <Tag color="error" className="ml-2">已逾期</Tag>}
                </span>}
              </Link>
            </li>)}</ul>
          </section>)}
        </>}
      </div>
    </Drawer>
  </>
}
