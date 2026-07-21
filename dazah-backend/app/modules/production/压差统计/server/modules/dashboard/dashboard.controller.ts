import { Controller, Get, Req } from '@nestjs/common';
import { NeedLogin } from '@lark-apaas/fullstack-nestjs-core';
import { DashboardService } from './dashboard.service';
import type { DashboardStats } from '@shared/api.interface';

@Controller('api/dashboard')
@NeedLogin()
export class DashboardController {
  constructor(private readonly dashboardService: DashboardService) {}

  @Get('stats')
  async getStats(@Req() req: any): Promise<DashboardStats> {
    return this.dashboardService.getStats(req.userContext);
  }
}
