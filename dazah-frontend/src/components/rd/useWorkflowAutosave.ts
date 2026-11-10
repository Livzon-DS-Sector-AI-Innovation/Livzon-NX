import { useCallback, useEffect, useRef, useState } from 'react'

export function useWorkflowAutosave(saveDraft: () => Promise<void>) {
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const pending = useRef(Promise.resolve())
  const running = useRef(false)
  const [saving, setSaving] = useState(false)
  const enqueue = useCallback((save: () => Promise<void>) => {
    const next = pending.current.then(save, save)
    pending.current = next
    return next
  }, [])

  useEffect(() => {
    if (saving) return
    const scheduled = setTimeout(() => {
      void enqueue(saveDraft).catch(error => console.error('工作流自动保存失败', error))
    }, 2000)
    timer.current = scheduled
    return () => clearTimeout(scheduled)
  }, [enqueue, saveDraft, saving])

  const runBeforeExit = async (save: (() => Promise<void>) | null, exit: () => void) => {
    if (running.current) return
    running.current = true
    setSaving(true)
    if (timer.current !== null) clearTimeout(timer.current)
    try {
      if (save) await enqueue(save)
      else await pending.current.catch(() => {})
      exit()
    } finally {
      running.current = false
      setSaving(false)
    }
  }
  return { runBeforeExit, saving }
}
