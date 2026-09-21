'use client'

import { useEffect } from 'react'
import { getUserErrorMessage } from '@/lib/user-error'

export default function GlobalError({
  error,
  unstable_retry,
}: {
  error: Error & { digest?: string }
  unstable_retry: () => void
}) {
  useEffect(() => {
    console.error('[应用] 页面渲染错误:', error)
  }, [error])

  return (
    <html lang="zh-CN">
      <body style={{ margin: 0, fontFamily: 'sans-serif', color: '#242424', background: '#f7f8fa' }}>
        <main style={{ maxWidth: 480, margin: '12vh auto', padding: 24 }}>
          <h1 style={{ fontSize: 22 }}>页面暂时无法显示</h1>
          <p>{getUserErrorMessage(error, '页面加载失败，请重试或刷新页面')}</p>
          {error.digest && <p style={{ fontSize: 12, color: '#666' }}>错误标识：{error.digest}</p>}
          <button type="button" onClick={() => unstable_retry()} style={{ padding: '8px 16px', cursor: 'pointer' }}>
            重试
          </button>
        </main>
      </body>
    </html>
  )
}
