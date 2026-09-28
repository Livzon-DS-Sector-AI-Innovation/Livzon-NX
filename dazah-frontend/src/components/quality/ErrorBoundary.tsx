'use client'

import { Component, type ReactNode } from 'react'
import { Button } from 'antd'
import PlatformNotice from '@/components/shared/PlatformNotice'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
  error?: Error
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="p-8 text-center">
          <PlatformNotice type="error" title="页面出错了" description={this.state.error?.message}
            action={<Button onClick={() => window.location.reload()}>刷新页面</Button>} />
        </div>
      )
    }
    return this.props.children
  }
}
