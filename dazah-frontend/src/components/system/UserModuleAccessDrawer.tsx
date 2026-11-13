'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Button, Drawer, Input, Skeleton, Table, Tag, Typography } from 'antd'
import Alert from '@/components/shared/PlatformNotice'
import { ReloadOutlined, SearchOutlined } from '@ant-design/icons'
import { getUserPagePermissions } from '@/actions/users'
import type { UserPagePermissionsOut } from '@/actions/users'
import { moduleMenus } from '@/lib/menu-config'
import { pagePermissionTierLabel } from '@/lib/page-permission-editor'
import styles from './UserModuleAccessDrawer.module.css'

const { Text, Title } = Typography

export interface ModuleAccessUser {
  id: string
  name: string
  isSystemAdmin: boolean
}

export default function UserModuleAccessDrawer({ user, open, onClose }: {
  user: ModuleAccessUser | null
  open: boolean
  onClose: () => void
}) {
  const sessionVersion = useRef(0)
  const userId = user?.id
  const [result, setResult] = useState<UserPagePermissionsOut | null>(null)
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')

  const load = useCallback(async () => {
    if (!userId) return
    const version = ++sessionVersion.current
    setLoading(true)
    setResult(null)
    setErrorMessage('')
    try {
      const next = await getUserPagePermissions(userId)
      if (version !== sessionVersion.current) return
      if (next.user_id !== userId) throw new Error('用户授权返回对象不一致，请重新加载')
      setResult(next)
    } catch (error) {
      if (version !== sessionVersion.current) return
      setErrorMessage(error instanceof Error ? error.message : '加载有效权限失败')
    } finally {
      if (version === sessionVersion.current) setLoading(false)
    }
  }, [userId])

  useEffect(() => {
    if (!open) return
    const timeoutId = window.setTimeout(() => { setSearch(''); void load() }, 0)
    return () => {
      window.clearTimeout(timeoutId)
      sessionVersion.current += 1
    }
  }, [load, open])

  const ready = Boolean(result && result.user_id === userId && !loading)
  const rows = useMemo(() => moduleMenus.map((module) => {
    const grants = (result?.grants || []).filter((grant) =>
      grant.module_code === module.moduleCode && grant.permissions?.includes('access'))
    return { moduleCode: module.moduleCode, name: module.label, grants,
      allowed: Boolean(user?.isSystemAdmin || grants.length) }
  }), [result, user?.isSystemAdmin])
  const allowedCount = rows.filter((row) => row.allowed).length
  const filteredRows = rows.filter((row) => !search.trim() ||
    [row.name, row.moduleCode].some((value) => value.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase())))
  const names = new Map((result?.definitions || []).map((page) => [page.page_key, page.page_name]))

  return <Drawer rootClassName={styles.drawer} open={open} onClose={onClose}
    placement="right" size="min(560px, 100vw)" destroyOnHidden
    title={<Title level={4} className={styles.title}>有效权限 · {user?.name || '用户'}</Title>}
    closable={{ placement: 'end', 'aria-label': '关闭' }}
    extra={<Button size="small" icon={<ReloadOutlined />} loading={loading} onClick={() => void load()}>刷新</Button>}>
    <div className={styles.body}>
      {errorMessage && <Alert type="error" showIcon title={errorMessage}
        action={<Button size="small" disabled={loading} onClick={() => void load()}>重新加载</Button>} />}
      {loading || (open && userId && !ready && !errorMessage) ? <Skeleton active paragraph={{ rows: 8 }} />
        : ready && <section aria-label="有效模块与页面权限">
            <div className={styles.toolbar}>
              <div className={styles.summary}>
                <Text strong>已开通 {allowedCount} 个模块</Text>
                <Text type="secondary">授权版本 {result?.grant_version}</Text>
              </div>
              <Input size="small" prefix={<SearchOutlined />} allowClear value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="搜索模块名称或编码" aria-label="搜索模块" className={styles.search} />
            </div>
            {allowedCount === 0 && <Text type="secondary" className={styles.emptyAccess}>
              尚无可访问页面，请分配角色或配置页面权限。
            </Text>}
            <Table className={styles.moduleTable} rowKey="moduleCode" dataSource={filteredRows}
              pagination={false} size="small" tableLayout="fixed" scroll={{ x: 320 }}
              columns={[
                { title: '模块', dataIndex: 'name', key: 'name' },
                { title: '入口状态', key: 'access', width: 112, render: (_, row) =>
                  row.allowed ? <Tag color="success">自动开通</Tag> : <Text type="secondary">无可访问页面</Text> },
                { title: '可访问页面', key: 'pages', width: 96, align: 'right', render: (_, row) => row.grants.length },
              ]}
              locale={{ emptyText: <Text type="secondary">没有匹配的模块，请调整搜索条件。</Text> }}
              expandable={{ showExpandColumn: rows.some((row) => row.grants.length > 0), columnWidth: 40,
                rowExpandable: (row) => Boolean(row.grants.length),
                expandedRowRender: (row) => <div className={styles.pageDetails}><Table rowKey="page_key" dataSource={row.grants}
                  pagination={false} size="small" tableLayout="fixed" columns={[
                    { title: '页面', key: 'page', render: (_, grant) => names.get(grant.page_key) || grant.page_key },
                    { title: '权限', key: 'permission', width: 72, render: (_, grant) => pagePermissionTierLabel(grant.permissions || []) },
                    { title: '来源', key: 'source', render: (_, grant) => grant.source === 'user' ? '用户覆盖'
                      : grant.source === 'super_admin' ? '管理员' : grant.source_role_names?.join('、') || '角色基线' },
                  ]} /></div> }} />
          </section>}
    </div>
  </Drawer>
}
