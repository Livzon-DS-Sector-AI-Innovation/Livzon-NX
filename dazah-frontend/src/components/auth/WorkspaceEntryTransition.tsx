'use client'

import { usePathname } from 'next/navigation'
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'

import styles from './WorkspaceEntryTransition.module.css'

const EntryContext = createContext<(target: string, frame: ReactNode) => void>(() => {})
const REVEAL_DURATION_MS = 800
const NAVIGATION_TIMEOUT_MS = 12_000

export const useWorkspaceEntryTransition = () => useContext(EntryContext)

export function WorkspaceEntryTransition({ children }: { children: ReactNode }) {
  const pathname = usePathname()
  const [entry, setEntry] = useState<{ from: string; target: string; frame: ReactNode } | null>(null)
  const [isSlow, setIsSlow] = useState(false)
  const revealing = entry !== null && pathname !== entry.from

  const beginEntry = useCallback((target: string, frame: ReactNode) => {
    setIsSlow(false)
    setEntry({ from: pathname, target, frame })
  }, [pathname])

  useEffect(() => {
    if (!entry) return
    // Preserve the verified authentication screen until the new route commits.
    // Cleanup uses a timer rather than animation events, so hidden tabs and
    // reduced-motion preferences cannot leave an invisible interaction blocker.
    const timer = window.setTimeout(() => {
      if (revealing) setEntry(null)
      else setIsSlow(true)
    }, revealing
      ? window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : REVEAL_DURATION_MS
      : NAVIGATION_TIMEOUT_MS)
    return () => window.clearTimeout(timer)
  }, [entry, revealing])

  return (
    <EntryContext value={beginEntry}>
      <div className={styles.content} inert={entry !== null} aria-busy={entry !== null || undefined}>
        {children}
      </div>
      {entry && (
        <div className={styles.cover} data-phase={revealing ? 'revealing' : 'waiting'} data-appearance="fixed-light">
          <div className={styles.curtain} aria-hidden="true" inert>
            {entry.frame}
          </div>
          <span className={styles.status} role="status" aria-live="polite">身份验证成功，正在进入工作台。</span>
          {isSlow && !revealing && (
            <div className={styles.recovery}>
              <span role="status">工作台加载较慢，请检查网络后重试。</span>
              <a className={styles.retry} href={entry.target}>重新打开工作台</a>
            </div>
          )}
        </div>
      )}
    </EntryContext>
  )
}
