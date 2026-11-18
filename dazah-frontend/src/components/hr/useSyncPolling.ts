'use client'

import { useState, useCallback, useRef, useEffect } from 'react'
import { getActionErrorMessage } from '@/lib/server-action-result'
import { readBusinessErrorCode, uncertainWriteMessage, UserFacingError } from '@/lib/user-error'

interface SyncPollingOptions {
  /** Action that kicks off the sync (POST). Returns a response that may contain data.state for immediate completion. */
  syncAction: () => Promise<unknown>
  /** Action that checks sync status. Called every `interval` ms until completion, failure, or timeout. */
  pollAction: () => Promise<unknown>
  /** Maximum number of poll attempts (default 90). Set to 0 for unlimited. */
  maxPolls?: number
  /** Polling interval in milliseconds (default 2000). */
  interval?: number
  /** Called on successful completion with the status message and optional result data. */
  onSuccess?: (message: string, result?: unknown) => void
  /** Called on failure or timeout with an error message. */
  onError?: (message: string) => void
}

interface SyncStatusData {
  status?: string
  state?: string
  progress?: string
  message?: string
  result?: unknown
}

function toSyncResponse(value: unknown): { data?: SyncStatusData } {
  if (typeof value !== 'object' || value === null) return {}
  const data = (value as { data?: unknown }).data
  return typeof data === 'object' && data !== null
    ? { data: data as SyncStatusData }
    : {}
}

function syncFailureMessage(status: string, data: SyncStatusData | undefined): string {
  if (status === 'interrupted') return uncertainWriteMessage('同步')
  if (readBusinessErrorCode(data) === 'HR_FEISHU_CONTACT_NOT_CONFIGURED') {
    return '人事飞书应用未配置，请联系管理员检查人事飞书设置'
  }
  return '同步失败，请查看同步任务状态'
}

/**
 * Generic hook for "trigger an async sync, then poll status until complete" workflows.
 *
 * Used by HR components (DepartmentClient, FeishuContactListClient, ContractAlertBanner)
 * to eliminate duplicated setInterval/setTimeout polling logic.
 */
export function useSyncPolling(options: SyncPollingOptions) {
  const [isSyncing, setIsSyncing] = useState(false)
  const optionsRef = useRef(options)

  useEffect(() => {
    optionsRef.current = options
  }, [options])

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const attemptsRef = useRef(0)
  const cancelledRef = useRef(false)

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
  }, [])

  const startSync = useCallback(() => {
    const { syncAction, pollAction, maxPolls = 90, interval = 2000, onSuccess, onError } = optionsRef.current
    setIsSyncing(true)
    cancelledRef.current = false
    attemptsRef.current = 0
    clearTimer()

    const handleError = (msg: string) => {
      if (cancelledRef.current) return
      setIsSyncing(false)
      onError?.(msg)
    }

    const poll = async () => {
      if (cancelledRef.current) return
      attemptsRef.current += 1
      if (maxPolls > 0 && attemptsRef.current > maxPolls) {
        handleError('暂未确认同步结果，请稍后刷新页面查看同步状态')
        return
      }
      try {
        const statusRes = toSyncResponse(await pollAction())
        const status = statusRes.data?.status || statusRes.data?.state

        if (status === 'completed' || status === 'success') {
          if (cancelledRef.current) return
          setIsSyncing(false)
          const msg = statusRes.data?.progress || statusRes.data?.message || '同步完成'
          onSuccess?.(msg, statusRes.data?.result)
          return
        }
        if (status === 'failed' || status === 'error' || status === 'interrupted') {
          handleError(syncFailureMessage(status, statusRes.data))
          return
        }
        // Still running, continue polling
        timerRef.current = setTimeout(poll, interval)
      } catch (error) {
        if (cancelledRef.current) return
        if (error instanceof UserFacingError) {
          handleError(error.message)
          return
        }
        // Query failed (network error, etc.) — retry with longer interval
        timerRef.current = setTimeout(poll, interval >= 3000 ? interval : 3000)
      }
    }

    syncAction()
      .then((value) => {
        const res = toSyncResponse(value)
        if (cancelledRef.current) return
        const status = res.data?.status || res.data?.state
        // Check for immediate completion/failure (e.g. syncAction returns final status directly)
        if (status === 'completed' || status === 'success') {
          setIsSyncing(false)
          const msg = res.data?.progress || res.data?.message || ''
          onSuccess?.(msg, res.data?.result)
          return
        }
        if (status === 'failed' || status === 'error' || status === 'interrupted') {
          handleError(syncFailureMessage(status, res.data))
          return
        }
        // Status is 'running' or undefined — start polling
        timerRef.current = setTimeout(poll, interval)
      })
      .catch((err: unknown) => {
        if (cancelledRef.current) return
        handleError(getActionErrorMessage(err, '同步'))
      })
  }, [clearTimer])

  // Cleanup on unmount: cancel any in-flight polling
  useEffect(() => {
    return () => {
      cancelledRef.current = true
      clearTimer()
    }
  }, [clearTimer])

  return { isSyncing, startSync }
}
