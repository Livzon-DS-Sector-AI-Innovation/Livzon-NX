import { axiosForBackend } from '@lark-apaas/client-toolkit/utils/getAxiosForBackend';
import type { DashboardStats } from '@shared/api.interface';

export async function getDashboardStats(): Promise<DashboardStats> {
  const response = await axiosForBackend({
    url: '/api/dashboard/stats',
    method: 'GET',
  });
  return response.data;
}
