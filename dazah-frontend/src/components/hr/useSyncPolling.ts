'use client'

import { useState, useCallback, useRef, useEffect } from 'react'

interface SyncPollingOptions {
  /** Action that kicks off the sync (POST). Returns a response that may contain data.state for immediate completion. */
  syncAction: () => Promise<any>
  /** Action that checks sync status. Called every `interval` ms until completion, failure, or timeout. */
  pollAction: () => Promise<any>
  /** Maximum number of poll attempts (default 90). Set to 0 for unlimited. */
  maxPolls?: number
  /** Polling interval in milliseconds (default 2000). */
  interval?: number
  /** Called on successful completion with the status message and optional result data. */
  onSuccess?: (message: string, result?: any) => void
  /** Called on failure or timeout with an error message. */
  onError?: (message: string) => void
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
        handleError('同步超时，请稍后刷新页面重试')
        return
      }
      try {
        const statusRes = await pollAction()
        const status = statusRes.data?.status || statusRes.data?.state

        if (status === 'completed' || status === 'success') {
          if (cancelledRef.current) return
          setIsSyncing(false)
          const msg = statusRes.data?.progress || statusRes.data?.message || '同步完成'
          onSuccess?.(msg, statusRes.data?.result)
          return
        }
        if (status === 'failed' || status === 'error') {
          if (cancelledRef.current) return
          handleError(statusRes.data?.progress || statusRes.data?.message || '同步失败')
          return
        }
        // Still running, continue polling
        timerRef.current = setTimeout(poll, interval)
      } catch {
        // Query failed (network error, etc.) — retry with longer interval
        timerRef.current = setTimeout(poll, interval >= 3000 ? interval : 3000)
      }
    }

    syncAction()
      .then((res) => {
        if (cancelledRef.current) return
        const status = res.data?.status || res.data?.state
        // Check for immediate completion/failure (e.g. syncAction returns final status directly)
        if (status === 'completed' || status === 'success') {
          setIsSyncing(false)
          const msg = res.data?.progress || res.data?.message || ''
          onSuccess?.(msg, res.data?.result)
          return
        }
        if (status === 'failed' || status === 'error') {
          handleError(res.data?.progress || res.data?.message || '同步失败')
          return
        }
        // Status is 'running' or undefined — start polling
        timerRef.current = setTimeout(poll, interval)
      })
      .catch((err: any) => {
        if (cancelledRef.current) return
        handleError(err.message || '同步失败')
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
