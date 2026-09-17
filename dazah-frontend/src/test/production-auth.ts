import { useAuthStore } from '@/stores/auth'

/** Give page-level production tests an authenticated user for their existing UI flows. */
export function setProductionAdminForTest() {
  useAuthStore.getState().setUser({
    id: 'production-test-admin',
    name: '生产测试管理员',
    role: 'admin',
  })
}

export function clearProductionAuthForTest() {
  useAuthStore.getState().clearUser()
}
