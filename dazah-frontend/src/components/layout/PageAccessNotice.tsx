import PlatformNotice from '@/components/shared/PlatformNotice'
import { MENU_PAGE_UNAVAILABLE, PAGE_NOT_FOUND, QUERY_PERMISSION_REQUIRED, type PageAccessNoticeReason } from '@/lib/page-access-notice'
import styles from './PageAccessNotice.module.css'

const noticeCopy = {
  [QUERY_PERMISSION_REQUIRED]: {
    title: '当前菜单仅授予入口权限。',
    message: '查看业务数据请联系管理员开通查询权限。',
  },
  [MENU_PAGE_UNAVAILABLE]: {
    title: '页面暂未开放',
    message: '请选择其他菜单继续操作。',
  },
  [PAGE_NOT_FOUND]: {
    title: '页面未找到',
    message: '请检查访问地址，或通过菜单前往其他页面。',
  },
}

export function PageAccessNotice({ reason }: { reason: PageAccessNoticeReason }) {
  const { title, message } = noticeCopy[reason]
  return (
    <div className={`${styles.noticeFrame} grid flex-1 place-items-center px-2 py-6`}>
      <PlatformNotice
        type="info"
        surface="custom"
        className={styles.card}
        title={<>
          <span className={styles.heading} role="heading" aria-level={1}>{title}</span>
          <span className={styles.body}>{message}</span>
        </>}
        showRulesLink={false}
      />
    </div>
  )
}
