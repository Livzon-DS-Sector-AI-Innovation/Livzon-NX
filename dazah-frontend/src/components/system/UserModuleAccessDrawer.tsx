'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Button, Drawer, Empty, Input, Skeleton, Table, Tag, Typography } from 'antd'
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
    placement="right" size="min(820px, 100vw)" destroyOnHidden
    title={<div>
      <Title level={4} className={styles.title}>有效权限 · {user?.name || '用户'}</Title>
      <Text type="secondary" className={styles.subtitle}>角色与用户页面覆盖的最终生效结果</Text>
    </div>}
    extra={<Button icon={<ReloadOutlined />} loading={loading} onClick={() => void load()}>刷新</Button>}
    footer={<div className={styles.footer}><Button onClick={onClose}>关闭</Button></div>}>
    <div className={styles.body}>
      <Alert className={styles.rulesNotice} type="info" showIcon
        title="模块入口随有效页面访问权限自动生效，无需单独开通。"
        description="多个角色的页面权限合并，用户页面覆盖优先。模块内至少一个页面具有有效访问权限时，入口自动开通；撤销最后一个可访问页面后，入口自动关闭。系统管理员默认拥有全部模块访问权限。本页只展示已保存的有效结果，权限调整请通过角色分配或页面权限进行。" />
      {errorMessage && <Alert type="error" showIcon title={errorMessage}
        action={<Button size="small" disabled={loading} onClick={() => void load()}>重新加载</Button>} />}
      {loading || (open && userId && !ready && !errorMessage) ? <Skeleton active paragraph={{ rows: 8 }} />
        : ready && <>
          <div className={styles.summary}>
            <Text strong>已开通 {allowedCount} 个模块</Text>
            <Text type="secondary">授权版本 {result?.grant_version}</Text>
          </div>
          {!allowedCount && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="尚无可访问页面，请分配角色或配置页面权限。" />}
          <section aria-label="有效模块与页面权限">
            <div className={styles.toolbar}>
              <Title level={5}>业务模块</Title>
              <Input prefix={<SearchOutlined />} allowClear value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="搜索模块名称或编码" aria-label="搜索模块" className={styles.search} />
            </div>
            <Table className={styles.moduleTable} rowKey="moduleCode" dataSource={filteredRows}
              pagination={false} size="middle" tableLayout="fixed" scroll={{ x: 520 }}
              columns={[
                { title: '模块', dataIndex: 'name', key: 'name' },
                { title: '入口状态', key: 'access', width: 150, render: (_, row) =>
                  <Tag color={row.allowed ? 'success' : 'default'}>{row.allowed ? '自动开通' : '无可访问页面'}</Tag> },
                { title: '可访问页面', key: 'pages', width: 120, render: (_, row) => row.grants.length },
              ]}
              locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有匹配的模块，请调整搜索条件。" /> }}
              expandable={{ rowExpandable: (row) => Boolean(row.grants.length),
                expandedRowRender: (row) => <div className={styles.pageDetails}><Table rowKey="page_key" dataSource={row.grants}
                  pagination={false} size="small" scroll={{ x: 520 }} columns={[
                    { title: '页面', key: 'page', render: (_, grant) => names.get(grant.page_key) || grant.page_key },
                    { title: '权限', key: 'permission', width: 110, render: (_, grant) => pagePermissionTierLabel(grant.permissions || []) },
                    { title: '来源', key: 'source', render: (_, grant) => grant.source === 'user' ? '用户覆盖'
                      : grant.source === 'super_admin' ? '管理员' : grant.source_role_names?.join('、') || '角色基线' },
                  ]} /></div> }} />
          </section>
        </>}
    </div>
  </Drawer>
}
