import { Controller, Get, Post, Patch, Delete, Param, Body, Req } from '@nestjs/common';
import { NeedLogin } from '@lark-apaas/fullstack-nestjs-core';
import { OcrTaskService } from './ocr-task.service';
import type {
  OcrTaskItem,
  CreateOcrTaskRequest,
  SubmitOcrTaskResultRequest,
  OcrSubmitResponse,
  OcrResultData,
} from '@shared/api.interface';

@Controller('api/ocr-tasks')
export class OcrTaskController {
  constructor(private readonly ocrTaskService: OcrTaskService) {}

  @Post()
  @NeedLogin()
  async create(
    @Req() req: any,
    @Body() dto: CreateOcrTaskRequest,
  ): Promise<{ taskId: string }> {
    const userId: string = req.userContext?.userId ?? '';
    return this.ocrTaskService.create(userId, dto);
  }

  @Get()
  @NeedLogin()
  async list(@Req() req: any): Promise<OcrTaskItem[]> {
    const userId: string = req.userContext?.userId ?? '';
    return this.ocrTaskService.listByUser(userId);
  }

  @Get(':id')
  @NeedLogin()
  async detail(@Req() req: any, @Param('id') id: string): Promise<OcrTaskItem> {
    const userId: string = req.userContext?.userId ?? '';
    return this.ocrTaskService.detail(userId, id);
  }

  @Post(':id/result')
  @NeedLogin()
  async updateResult(
    @Req() req: any,
    @Param('id') id: string,
    @Body() body: OcrResultData,
  ): Promise<{ success: boolean }> {
    const userId: string = req.userContext?.userId ?? '';
    await this.ocrTaskService.updateResult(userId, id, body);
    return { success: true };
  }

  @Post(':id/error')
  @NeedLogin()
  async updateError(
    @Req() req: any,
    @Param('id') id: string,
    @Body() body: { errorMessage: string },
  ): Promise<{ success: boolean }> {
    const userId: string = req.userContext?.userId ?? '';
    await this.ocrTaskService.updateError(userId, id, body.errorMessage);
    return { success: true };
  }

  @Patch(':id/cancel')
  @NeedLogin()
  async cancel(
    @Req() req: any,
    @Param('id') id: string,
  ): Promise<{ success: boolean }> {
    const userId: string = req.userContext?.userId ?? '';
    await this.ocrTaskService.cancel(userId, id);
    return { success: true };
  }

  @Post(':id/retry')
  @NeedLogin()
  async retry(
    @Req() req: any,
    @Param('id') id: string,
  ): Promise<{ taskId: string }> {
    const userId: string = req.userContext?.userId ?? '';
    return this.ocrTaskService.retry(userId, id);
  }

  @Delete(':id')
  @NeedLogin()
  async remove(
    @Req() req: any,
    @Param('id') id: string,
  ): Promise<{ success: boolean }> {
    const userId: string = req.userContext?.userId ?? '';
    await this.ocrTaskService.remove(userId, id);
    return { success: true };
  }

  @Post(':id/submit')
  @NeedLogin()
  async submit(
    @Req() req: any,
    @Param('id') id: string,
    @Body() dto: SubmitOcrTaskResultRequest,
  ): Promise<OcrSubmitResponse> {
    const userId: string = req.userContext?.userId ?? '';
    return this.ocrTaskService.submitResult(userId, id, dto);
  }
}
