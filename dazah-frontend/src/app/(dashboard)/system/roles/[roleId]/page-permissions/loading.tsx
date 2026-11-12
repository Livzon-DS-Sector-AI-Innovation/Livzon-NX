import styles from "@/components/system/RolePagePermissionsWorkbench.module.css"

export default function RolePagePermissionsLoading() {
  return <div className={`${styles.workbench} ${styles.loadingShell}`} role="status" aria-label="正在加载页面权限">
    <header className={styles.header} aria-hidden="true">
      <div className={styles.heading}>
        <span className={styles.headingIcon} />
        <h1>页面权限基线配置</h1>
      </div>
      <div className={styles.loadingStats}>
        {[0, 1, 2, 3].map((index) => <span key={index} className={styles.loadingBlock} />)}
      </div>
    </header>
    <div className={styles.loadingModuleTabs} aria-hidden="true">
      {[0, 1, 2, 3, 4].map((index) => <span key={index} className={styles.loadingBlock} />)}
    </div>
    <div className={styles.loadingToolbar} aria-hidden="true">
      {[0, 1, 2].map((index) => <span key={index} className={styles.loadingBlock} />)}
    </div>
    <div className={styles.columns} aria-hidden="true">
      {[5, 4, 3].map((rows) => <div key={rows} className={`${styles.panel} ${styles.loadingPanel}`}>
        {Array.from({ length: rows }, (_, index) => <span key={index} className={styles.loadingBlock} />)}
      </div>)}
    </div>
    <div className={`${styles.footer} ${styles.loadingFooter}`} aria-hidden="true">
      <span className={`${styles.reason} ${styles.loadingBlock}`} />
      <span className={styles.loadingBlock} />
      <span className={styles.loadingBlock} />
    </div>
  </div>
}
