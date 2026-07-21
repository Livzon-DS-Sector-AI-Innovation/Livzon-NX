import { Controller, Get, Post, Patch, Delete, Param, Query, Body, Req } from '@nestjs/common';
import { NeedLogin, CanRole } from '@lark-apaas/fullstack-nestjs-core';
import { PressureRecordsService } from './pressure-records.service';
import type {
  PaginatedResponse,
  PressureRecordItem,
  CreateManualRecordRequest,
  CreateOcrRecordRequest,
  OcrSubmitResponse,
  AuditRequest,
  BatchAuditRequest,
  BatchAuditResponse,
  PressureRecordQuery,
  BatchManualEntryRequest,
  BatchManualEntryResponse,
  AreaExportData,
  DeleteRecordsRequest,
  DeleteRecordsResponse,
  MergedPressureResponse,
  DeleteMergedRowRequest,
  BatchDeleteMergedRowsRequest,
  UpdateMergedRowRequest,
  UpdateMergedRowResponse,
} from '@shared/api.interface';

@Controller('api/pressure-records')
export class PressureRecordsController {
  constructor(private readonly pressureRecordsService: PressureRecordsService) {}

  @Get()
  @NeedLogin()
  async list(
    @Req() req: any,
    @Query('area') area?: string,
    @Query('startDate') startDate?: string,
    @Query('endDate') endDate?: string,
    @Query('pointId') pointId?: string,
    @Query('inputType') inputType?: string,
    @Query('page') page?: string,
    @Query('pageSize') pageSize?: string,
  ): Promise<PaginatedResponse<PressureRecordItem>> {
    const query: PressureRecordQuery = {
      area: area as any,
      startDate,
      endDate,
      pointId,
      inputType: inputType as any,
      page: page ? parseInt(page, 10) : 1,
      pageSize: pageSize ? parseInt(pageSize, 10) : 20,
    };
    return this.pressureRecordsService.list(req.userContext, query);
  }

  @Get('merged')
  @NeedLogin()
  async listMerged(
    @Req() req: any,
    @Query('area') area?: string,
    @Query('startDate') startDate?: string,
    @Query('endDate') endDate?: string,
    @Query('pointId') pointId?: string,
    @Query('inputType') inputType?: string,
    @Query('page') page?: string,
    @Query('pageSize') pageSize?: string,
  ): Promise<MergedPressureResponse> {
    const query: PressureRecordQuery = {
      area: area as any,
      startDate,
      endDate,
      pointId,
      inputType: inputType as any,
      page: page ? parseInt(page, 10) : 1,
      pageSize: pageSize ? parseInt(pageSize, 10) : 20,
    };
    return this.pressureRecordsService.listMerged(req.userContext, query);
  }

  @Post('merged/delete')
  @NeedLogin()
  async deleteMergedRow(
    @Body() dto: DeleteMergedRowRequest,
  ): Promise<{ successCount: number; success: boolean }> {
    return this.pressureRecordsService.deleteMergedRow(dto.pointId, dto.date);
  }

  @Post('merged/batch-delete')
  @NeedLogin()
  async batchDeleteMergedRows(
    @Body() dto: BatchDeleteMergedRowsRequest,
  ): Promise<{ successCount: number; failCount: number; success: boolean }> {
    return this.pressureRecordsService.batchDeleteMergedRows(dto.rows);
  }

  @Post('merged/update')
  @NeedLogin()
  async updateMergedRow(
    @Body() dto: UpdateMergedRowRequest,
  ): Promise<UpdateMergedRowResponse> {
    return this.pressureRecordsService.updateMergedRow(dto);
  }

  @Get(':id')
  @NeedLogin()
  async detail(@Req() req: any, @Param('id') id: string): Promise<PressureRecordItem> {
    return this.pressureRecordsService.detail(req.userContext, id);
  }

  @Post('manual')
  @NeedLogin()
  async createManual(
    @Req() req: any,
    @Body() dto: CreateManualRecordRequest,
  ): Promise<{ id: string; success: boolean }> {
    return this.pressureRecordsService.createManual(req.userContext, dto);
  }

  @Post('manual/batch')
  @NeedLogin()
  async createBatchManual(
    @Req() req: any,
    @Body() dto: BatchManualEntryRequest,
  ): Promise<BatchManualEntryResponse> {
    return this.pressureRecordsService.createBatchManual(req.userContext, dto);
  }

  @Get('export/by-area')
  @NeedLogin()
  async exportByArea(
    @Query('area') area?: string,
    @Query('startDate') startDate?: string,
    @Query('endDate') endDate?: string,
    @Query('pointId') pointId?: string,
  ): Promise<AreaExportData[]> {
    const query: PressureRecordQuery = {
      area: area as any,
      startDate,
      endDate,
      pointId,
    };
    return this.pressureRecordsService.getExportByArea(query);
  }

  @Post('ocr')
  @NeedLogin()
  async createOcr(
    @Req() req: any,
    @Body() dto: CreateOcrRecordRequest,
  ): Promise<OcrSubmitResponse> {
    return this.pressureRecordsService.createOcr(req.userContext, dto);
  }

  @Patch(':id/audit')
  @NeedLogin()
  @CanRole(['admin'])
  async audit(
    @Param('id') id: string,
    @Body() dto: AuditRequest,
  ): Promise<{ success: boolean }> {
    return this.pressureRecordsService.audit(id, dto);
  }

  @Patch('batch-audit')
  @NeedLogin()
  @CanRole(['admin'])
  async batchAudit(@Body() dto: BatchAuditRequest): Promise<BatchAuditResponse> {
    return this.pressureRecordsService.batchAudit(dto);
  }

  @Delete(':id')
  @NeedLogin()
  @CanRole(['admin'])
  async remove(@Param('id') id: string): Promise<{ success: boolean }> {
    return this.pressureRecordsService.remove(id);
  }

  @Post('batch-delete')
  @NeedLogin()
  @CanRole(['admin'])
  async batchRemove(@Body() dto: DeleteRecordsRequest): Promise<DeleteRecordsResponse> {
    return this.pressureRecordsService.batchRemove(dto.ids);
  }
}
