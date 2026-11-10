'use client'

import { Component, type ReactNode } from 'react'
import { Button } from 'antd'
import PlatformNotice from '@/components/shared/PlatformNotice'

interface Props {
  children: ReactNode
}

interface State {
  error: Error | null
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  render() {
    if (this.state.error) {
      return (
        <div className="p-8 text-center">
          <PlatformNotice type="error" title="页面出错了" description={this.state.error.message}
            action={<Button onClick={() => this.setState({ error: null })}>重试</Button>} />
        </div>
      )
    }
    return this.props.children
  }
}
