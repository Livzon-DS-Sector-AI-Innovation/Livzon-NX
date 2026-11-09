import { Button, Result } from 'antd'
import { ActionRequestError } from '@/lib/server-action-result'
import { getUserErrorMessage } from '@/lib/user-error'

export function isEquipmentQueryAccessError(
  error: unknown,
): error is ActionRequestError & { status: 401 | 403 } {
  return error instanceof ActionRequestError && (error.status === 401 || error.status === 403)
}

export function EquipmentQueryFailure({ status }: { status: 401 | 403 }) {
  const loginRequired = status === 401
  return (
    <Result
      status={loginRequired ? 'warning' : '403'}
      title={getUserErrorMessage(undefined, undefined, status)}
      extra={
        <Button href={loginRequired ? '/login' : '/'}>
          {loginRequired ? '重新登录' : '返回平台'}
        </Button>
      }
    />
  )
}
