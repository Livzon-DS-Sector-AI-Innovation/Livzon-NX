import { Injectable, Inject, Logger, NotFoundException, BadRequestException } from '@nestjs/common';
import { DRIZZLE_DATABASE, type PostgresJsDatabase } from '@lark-apaas/fullstack-nestjs-core';
import { ocrTask, pressureRecord, pointMapping, notification } from '@server/database/schema';
import { eq, and, desc } from 'drizzle-orm';
import type {
  OcrTaskItem,
  OcrResultData,
  CreateOcrTaskRequest,
  SubmitOcrTaskResultRequest,
  OcrSubmitResponse,
} from '@shared/api.interface';

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function assertValidUuid(value: string, field: string): void {
  if (!UUID_RE.test(value)) {
    throw new BadRequestException(`Invalid ${field}: ${value}`);
  }
}

@Injectable()
export class OcrTaskService {
  private readonly logger = new Logger(OcrTaskService.name);

  constructor(
    @Inject(DRIZZLE_DATABASE) private readonly db: PostgresJsDatabase,
  ) {}

  async create(
    userId: string,
    dto: CreateOcrTaskRequest,
  ): Promise<{ taskId: string }> {
    const result = await this.db
      .insert(ocrTask)
      .values({
        imageUrl: dto.imageUrl,
        status: 'pending',
        creator: userId,
      })
      .returning({ id: ocrTask.id });

    const taskId = result[0]?.id ?? '';
    this.logger.log(`OCR task created: ${taskId} by user ${userId}`);
    return { taskId };
  }

  async listByUser(userId: string): Promise<OcrTaskItem[]> {
    const rows = await this.db
      .select({
        id: ocrTask.id,
        status: ocrTask.status,
        imageUrl: ocrTask.imageUrl,
        result: ocrTask.result,
        errorMessage: ocrTask.errorMessage,
        batchId: ocrTask.batchId,
        createdAt: ocrTask.createdAt,
      })
      .from(ocrTask)
      .where(eq(ocrTask.creator, userId))
      .orderBy(desc(ocrTask.createdAt))
      .limit(50);

    return rows.map((row) => ({
      id: row.id,
      status: row.status as OcrTaskItem['status'],
      imageUrl: row.imageUrl,
      result: row.result as OcrResultData | null,
      errorMessage: row.errorMessage,
      batchId: row.batchId,
      createdAt: row.createdAt.toISOString(),
    }));
  }

  async detail(userId: string, taskId: string): Promise<OcrTaskItem> {
    assertValidUuid(taskId, 'taskId');
    const rows = await this.db
      .select({
        id: ocrTask.id,
        status: ocrTask.status,
        imageUrl: ocrTask.imageUrl,
        result: ocrTask.result,
        errorMessage: ocrTask.errorMessage,
        batchId: ocrTask.batchId,
        createdAt: ocrTask.createdAt,
      })
      .from(ocrTask)
      .where(
        and(
          eq(ocrTask.id, taskId),
          eq(ocrTask.creator, userId),
        ),
      )
      .limit(1);

    if (rows.length === 0) {
      throw new NotFoundException('OCR任务不存在');
    }

    const row = rows[0];
    return {
      id: row.id,
      status: row.status as OcrTaskItem['status'],
      imageUrl: row.imageUrl,
      result: row.result as OcrResultData | null,
      errorMessage: row.errorMessage,
      batchId: row.batchId,
      createdAt: row.createdAt.toISOString(),
    };
  }

  async updateResult(
    userId: string,
    taskId: string,
    result: OcrResultData,
  ): Promise<void> {
    assertValidUuid(taskId, 'taskId');
    const rows = await this.db
      .select({ id: ocrTask.id, status: ocrTask.status })
      .from(ocrTask)
      .where(
        and(
          eq(ocrTask.id, taskId),
          eq(ocrTask.creator, userId),
        ),
      )
      .limit(1);

    if (rows.length === 0) {
      throw new NotFoundException('OCR任务不存在');
    }

    if (rows[0].status === 'cancelled') {
      throw new BadRequestException('任务已取消');
    }

    await this.db
      .update(ocrTask)
      .set({
        status: 'completed',
        result: result as any,
        updatedAt: new Date(),
      })
      .where(eq(ocrTask.id, taskId));

    await this.db.insert(notification).values({
      type: 'ocr_completed',
      title: 'OCR识别完成',
      message: `图片识别已完成，共识别到 ${result.records.length} 条记录，请前往查看`,
      targetUser: userId,
      relatedId: taskId,
      relatedType: 'ocr_task',
    });

    this.logger.log(`OCR task ${taskId} completed with ${result.records.length} records`);
  }

  async updateError(
    userId: string,
    taskId: string,
    errorMessage: string,
  ): Promise<void> {
    assertValidUuid(taskId, 'taskId');
    await this.db
      .update(ocrTask)
      .set({
        status: 'failed',
        errorMessage,
        updatedAt: new Date(),
      })
      .where(eq(ocrTask.id, taskId));

    await this.db.insert(notification).values({
      type: 'ocr_failed',
      title: 'OCR识别失败',
      message: `图片识别失败：${errorMessage}，请重新上传`,
      targetUser: userId,
      relatedId: taskId,
      relatedType: 'ocr_task',
    });

    this.logger.log(`OCR task ${taskId} failed: ${errorMessage}`);
  }

  async cancel(userId: string, taskId: string): Promise<void> {
    assertValidUuid(taskId, 'taskId');
    const rows = await this.db
      .select({ id: ocrTask.id, status: ocrTask.status })
      .from(ocrTask)
      .where(
        and(
          eq(ocrTask.id, taskId),
          eq(ocrTask.creator, userId),
        ),
      )
      .limit(1);

    if (rows.length === 0) {
      throw new NotFoundException('OCR任务不存在');
    }

    if (!['pending', 'processing'].includes(rows[0].status)) {
      throw new BadRequestException('只能取消待处理或处理中的任务');
    }

    await this.db
      .update(ocrTask)
      .set({ status: 'cancelled', updatedAt: new Date() })
      .where(eq(ocrTask.id, taskId));
  }

  async retry(userId: string, taskId: string): Promise<{ taskId: string }> {
    assertValidUuid(taskId, 'taskId');
    const rows = await this.db
      .select({ id: ocrTask.id, status: ocrTask.status, imageUrl: ocrTask.imageUrl })
      .from(ocrTask)
      .where(
        and(
          eq(ocrTask.id, taskId),
          eq(ocrTask.creator, userId),
        ),
      )
      .limit(1);

    if (rows.length === 0) {
      throw new NotFoundException('OCR任务不存在');
    }

    if (rows[0].status !== 'failed') {
      throw new BadRequestException('只能重试失败的任务');
    }

    await this.db
      .update(ocrTask)
      .set({
        status: 'pending',
        errorMessage: null,
        result: null,
        updatedAt: new Date(),
      })
      .where(eq(ocrTask.id, taskId));

    return { taskId };
  }

  async remove(userId: string, taskId: string): Promise<void> {
    assertValidUuid(taskId, 'taskId');
    const rows = await this.db
      .select({ id: ocrTask.id, status: ocrTask.status })
      .from(ocrTask)
      .where(
        and(
          eq(ocrTask.id, taskId),
          eq(ocrTask.creator, userId),
        ),
      )
      .limit(1);

    if (rows.length === 0) {
      throw new NotFoundException('OCR任务不存在');
    }

    if (rows[0].status === 'processing') {
      throw new BadRequestException('正在识别中的任务无法删除');
    }

    await this.db.delete(ocrTask).where(eq(ocrTask.id, taskId));
    this.logger.log(`OCR task ${taskId} deleted by user ${userId}`);
  }

  async submitResult(
    userId: string,
    taskId: string,
    dto: SubmitOcrTaskResultRequest,
  ): Promise<OcrSubmitResponse> {
    assertValidUuid(taskId, 'taskId');
    const taskRows = await this.db
      .select({ id: ocrTask.id, status: ocrTask.status })
      .from(ocrTask)
      .where(
        and(
          eq(ocrTask.id, taskId),
          eq(ocrTask.creator, userId),
        ),
      )
      .limit(1);

    if (taskRows.length === 0) {
      throw new NotFoundException('OCR任务不存在');
    }

    const batchId = crypto.randomUUID();
    let successCount = 0;

    for (const record of dto.records) {
      try {
        const mappingRows = await this.db
          .select()
          .from(pointMapping)
          .where(eq(pointMapping.pointId, record.pointId))
          .limit(1);

        const mapping = mappingRows[0];
          await this.db.insert(pressureRecord).values({
          pointId: record.pointId,
          area: record.area,
          pressureValue: record.pressureValue,
          standardPressure: record.standardPressure ?? mapping?.standardPressure ?? 0,
          recordTime: new Date(record.recordTime),
          inputType: 'ocr',
          status: 'pending',
          creator: userId,
          imageUrl: taskRows[0].id,
          batchId,
          remark: record.remark ?? null,
          timeSlot: record.timeSlot ?? null,
        });
        successCount++;
      } catch (err) {
        this.logger.error(`OCR record insert failed: ${JSON.stringify(err)}`);
      }
    }

    await this.db
      .update(ocrTask)
      .set({
        status: 'submitted',
        batchId,
        updatedAt: new Date(),
      })
      .where(eq(ocrTask.id, taskId));

    return {
      successCount,
      failCount: dto.records.length - successCount,
      success: true,
      batchId,
    };
  }
}
