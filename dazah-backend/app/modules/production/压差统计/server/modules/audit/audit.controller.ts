import { Controller, Get, Query, Req } from '@nestjs/common';
import { NeedLogin, CanRole } from '@lark-apaas/fullstack-nestjs-core';
import { AuditService } from './audit.service';
import type { AuditStats, PaginatedResponse, AuditRecordItem } from '@shared/api.interface';

@Controller('api/audit')
@NeedLogin()
export class AuditController {
  constructor(private readonly auditService: AuditService) {}

  @Get('stats')
  @CanRole(['admin'])
  async getStats(): Promise<AuditStats> {
    return this.auditService.getStats();
  }

  @Get('pending-records')
  @CanRole(['admin'])
  async getPendingRecords(
    @Req() req: any,
    @Query('page') page?: string,
    @Query('pageSize') pageSize?: string,
  ): Promise<PaginatedResponse<AuditRecordItem>> {
    void req;
    return this.auditService.getPendingRecords(
      page ? parseInt(page, 10) : 1,
      pageSize ? parseInt(pageSize, 10) : 20,
    );
  }
}
