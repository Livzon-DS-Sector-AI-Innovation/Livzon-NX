import { Injectable, Inject, NotFoundException, Logger } from '@nestjs/common';
import { DRIZZLE_DATABASE, type PostgresJsDatabase } from '@lark-apaas/fullstack-nestjs-core';
import { pressureRecord, pointMapping } from '@server/database/schema';
import { eq, and, gte, lte, desc, count, inArray, asc } from 'drizzle-orm';
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
  TemplateExportRow,
  AreaType,
  MergedPressureRow,
  MergedPressureResponse,
  DeleteMergedRowRequest,
  AuditStatus,
  UpdateMergedRowRequest,
  UpdateMergedRowResponse,
} from '@shared/api.interface';

@Injectable()
export class PressureRecordsService {
  private readonly logger = new Logger(PressureRecordsService.name);

  constructor(
    @Inject(DRIZZLE_DATABASE) private readonly db: PostgresJsDatabase,
  ) {}

  async list(
    userContext: any,
    query: PressureRecordQuery,
  ): Promise<PaginatedResponse<PressureRecordItem>> {
    const page = query.page ?? 1;
    const pageSize = query.pageSize ?? 20;
    const offset = (page - 1) * pageSize;

    const conditions = [];
    if (query.area) conditions.push(eq(pressureRecord.area, query.area));
    if (query.pointId) conditions.push(eq(pressureRecord.pointId, query.pointId));
    if (query.inputType) conditions.push(eq(pressureRecord.inputType, query.inputType));
    if (query.startDate) conditions.push(gte(pressureRecord.recordTime, new Date(query.startDate)));
    if (query.endDate) conditions.push(lte(pressureRecord.recordTime, new Date(query.endDate)));

    const whereClause = conditions.length > 0 ? and(...conditions) : undefined;

    const [items, totalResult] = await Promise.all([
      this.db
        .select()
        .from(pressureRecord)
        .where(whereClause)
        .orderBy(desc(pressureRecord.recordTime))
        .limit(pageSize)
        .offset(offset),
      this.db
        .select({ count: count() })
        .from(pressureRecord)
        .where(whereClause),
    ]);

    const total = Number(totalResult[0]?.count ?? 0);

    const mappedItems: PressureRecordItem[] = items.map((item) => ({
      id: item.id,
      pointId: item.pointId,
      area: item.area as PressureRecordItem['area'],
      pressureValue: item.pressureValue,
      standardPressure: item.standardPressure,
      recordTime: item.recordTime.toISOString(),
      inputType: item.inputType as PressureRecordItem['inputType'],
      status: item.status as PressureRecordItem['status'],
      rejectReason: item.rejectReason,
      creator: item.creator,
      imageUrl: item.imageUrl,
      remark: item.remark,
      batchId: item.batchId,
      timeSlot: item.timeSlot,
    }));

    return { items: mappedItems, total };
  }

  async detail(userContext: any, id: string): Promise<PressureRecordItem> {
    const rows = await this.db
      .select()
      .from(pressureRecord)
      .where(eq(pressureRecord.id, id))
      .limit(1);

    if (rows.length === 0) {
      throw new NotFoundException('记录不存在');
    }

    const item = rows[0];
    return {
      id: item.id,
      pointId: item.pointId,
      area: item.area as PressureRecordItem['area'],
      pressureValue: item.pressureValue,
      standardPressure: item.standardPressure,
      recordTime: item.recordTime.toISOString(),
      inputType: item.inputType as PressureRecordItem['inputType'],
      status: item.status as PressureRecordItem['status'],
      rejectReason: item.rejectReason,
      creator: item.creator,
      imageUrl: item.imageUrl,
      remark: item.remark,
      batchId: item.batchId,
      timeSlot: item.timeSlot,
    };
  }

  async createBatchManual(
    userContext: any,
    dto: BatchManualEntryRequest,
  ): Promise<BatchManualEntryResponse> {
    const userId: string = userContext?.userId ?? '';
    const batchId = crypto.randomUUID();
    let successCount = 0;
    let totalExpected = 0;

    const allPoints = await this.db
      .select()
      .from(pointMapping)
      .where(eq(pointMapping.area, dto.area));

    const pointMap = new Map(allPoints.map((p) => [p.pointId, p]));

    for (const row of dto.rows) {
      const recordDate = new Date(row.date);

      for (const [rawKey, value] of Object.entries(row.values)) {
        if (value == null) continue;
        totalExpected++;

        let pointId: string;
        let timeSlot: string | null = null;

        if (dto.timeSlots && dto.timeSlots.length > 0) {
          const sepIdx = rawKey.lastIndexOf('::');
          if (sepIdx > 0) {
            pointId = rawKey.slice(0, sepIdx);
            timeSlot = rawKey.slice(sepIdx + 2);
          } else {
            pointId = rawKey;
          }
        } else {
          pointId = rawKey;
        }

        const mapping = pointMap.get(pointId);
        const area = mapping?.area ?? dto.area;
        const standardPressure = mapping?.standardPressure ?? 0;

        try {
          await this.db.insert(pressureRecord).values({
            pointId,
            area,
            pressureValue: value,
            standardPressure,
            recordTime: recordDate,
            inputType: 'manual',
            status: 'pending',
            creator: userId,
            batchId,
            timeSlot,
            remark: dto.remark ?? null,
          });
          successCount++;
        } catch (err) {
          this.logger.error(`Batch insert failed: ${JSON.stringify(err)}`);
        }
      }
    }

    return {
      successCount,
      failCount: totalExpected - successCount,
      batchId,
    };
  }

  async getExportByArea(
    query: PressureRecordQuery,
  ): Promise<AreaExportData[]> {
    const conditions = [];
    if (query.area) conditions.push(eq(pressureRecord.area, query.area));
    if (query.startDate) conditions.push(gte(pressureRecord.recordTime, new Date(query.startDate)));
    if (query.endDate) conditions.push(lte(pressureRecord.recordTime, new Date(query.endDate)));
    if (query.pointId) conditions.push(eq(pressureRecord.pointId, query.pointId));

    const whereClause = conditions.length > 0 ? and(...conditions) : undefined;

    const records = await this.db
      .select({
        id: pressureRecord.id,
        pointId: pressureRecord.pointId,
        area: pressureRecord.area,
        pressureValue: pressureRecord.pressureValue,
        standardPressure: pressureRecord.standardPressure,
        recordTime: pressureRecord.recordTime,
        timeSlot: pressureRecord.timeSlot,
      })
      .from(pressureRecord)
      .where(whereClause)
      .orderBy(asc(pressureRecord.recordTime), asc(pressureRecord.pointId));

    const areaMap = new Map<string, {
      timeSlots: Set<string>;
      rowMap: Map<string, Map<string, number | null>>;
      standardMap: Map<string, number>;
    }>();

    for (const rec of records) {
      const area = rec.area;
      const dateStr = rec.recordTime.toISOString().slice(0, 10);
      const slot = rec.timeSlot || '默认';
      const rowKey = `${dateStr}|${rec.pointId}`;

      if (!areaMap.has(area)) {
        areaMap.set(area, {
          timeSlots: new Set(),
          rowMap: new Map(),
          standardMap: new Map(),
        });
      }

      const areaData = areaMap.get(area)!;
      areaData.timeSlots.add(slot);
      areaData.standardMap.set(rec.pointId, rec.standardPressure);

      if (!areaData.rowMap.has(rowKey)) {
        areaData.rowMap.set(rowKey, new Map());
      }
      areaData.rowMap.get(rowKey)!.set(slot, rec.pressureValue);
    }

    const result: AreaExportData[] = [];
    for (const [area, data] of areaMap.entries()) {
      const timeSlots = Array.from(data.timeSlots).sort();
      const rows: TemplateExportRow[] = [];

      const sortedKeys = Array.from(data.rowMap.keys()).sort();
      for (const rowKey of sortedKeys) {
        const [date, pointId] = rowKey.split('|');
        const values: Record<string, number | null> = {};
        for (const slot of timeSlots) {
          values[slot] = data.rowMap.get(rowKey)!.get(slot) ?? null;
        }
        const stdPressure = data.standardMap.get(pointId) ?? 0;
        rows.push({
          date,
          pointId,
          standardPressure: `≥${stdPressure}Pa`,
          values,
        });
      }

      result.push({
        area: area as AreaType,
        timeSlots,
        rows,
      });
    }

    return result;
  }

  async createManual(
    userContext: any,
    dto: CreateManualRecordRequest,
  ): Promise<{ id: string; success: boolean }> {
    const userId: string = userContext?.userId ?? '';

    const mappingRows = await this.db
      .select()
      .from(pointMapping)
      .where(eq(pointMapping.pointId, dto.pointId))
      .limit(1);

    const mapping = mappingRows[0];
    const area = mapping?.area ?? '';
    const standardPressure = mapping?.standardPressure ?? 0;

    const result = await this.db
      .insert(pressureRecord)
      .values({
        pointId: dto.pointId,
        area,
        pressureValue: dto.pressureValue,
        standardPressure,
        recordTime: new Date(dto.recordTime),
        inputType: 'manual',
        status: 'pending',
        creator: userId,
        timeSlot: dto.timeSlot ?? null,
        remark: dto.remark ?? null,
      })
      .returning({ id: pressureRecord.id });

    return { id: result[0]?.id ?? '', success: true };
  }

  async createOcr(
    userContext: any,
    dto: CreateOcrRecordRequest,
  ): Promise<OcrSubmitResponse> {
    const userId: string = userContext?.userId ?? '';
    let successCount = 0;

    for (const record of dto.records) {
      try {
        await this.db.insert(pressureRecord).values({
          pointId: record.pointId,
          area: record.area,
          pressureValue: record.pressureValue,
          standardPressure: record.standardPressure ?? 0,
          recordTime: new Date(record.recordTime),
          inputType: 'ocr',
          status: 'pending',
          creator: userId,
          imageUrl: dto.imageUrl,
          remark: record.remark ?? null,
        });
        successCount++;
      } catch (err) {
        this.logger.error(`OCR record insert failed: ${JSON.stringify(err)}`);
      }
    }

    return {
      successCount,
      failCount: dto.records.length - successCount,
      success: true,
    };
  }

  async audit(id: string, dto: AuditRequest): Promise<{ success: boolean }> {
    const result = await this.db
      .update(pressureRecord)
      .set({
        status: dto.status,
        rejectReason: dto.status === 'rejected' ? (dto.rejectReason ?? null) : null,
        updatedAt: new Date(),
      })
      .where(eq(pressureRecord.id, id))
      .returning({ id: pressureRecord.id });

    if (result.length === 0) {
      throw new NotFoundException('记录不存在');
    }

    this.logger.log(`Audit record ${id}: status=${dto.status}`);
    return { success: true };
  }

  async batchAudit(dto: BatchAuditRequest): Promise<BatchAuditResponse> {
    if (!dto.ids || dto.ids.length === 0) {
      return { successCount: 0, failCount: 0, success: true };
    }

    const updateData: Record<string, unknown> = {
      status: dto.status,
      rejectReason: dto.status === 'rejected' ? (dto.rejectReason ?? null) : null,
      updatedAt: new Date(),
    };

    const result = await this.db
      .update(pressureRecord)
      .set(updateData)
      .where(inArray(pressureRecord.id, dto.ids))
      .returning({ id: pressureRecord.id });

    const successCount = result.length;
    const failCount = dto.ids.length - successCount;

    this.logger.log(`Batch audit: ${successCount} succeeded, ${failCount} failed`);
    return { successCount, failCount, success: true };
  }

  async remove(id: string): Promise<{ success: boolean }> {
    const result = await this.db
      .delete(pressureRecord)
      .where(eq(pressureRecord.id, id))
      .returning({ id: pressureRecord.id });

    if (result.length === 0) {
      throw new NotFoundException('记录不存在');
    }

    this.logger.log(`Deleted pressure record ${id}`);
    return { success: true };
  }

  async listMerged(
    userContext: any,
    query: PressureRecordQuery,
  ): Promise<MergedPressureResponse> {
    const page = query.page ?? 1;
    const pageSize = query.pageSize ?? 20;

    const conditions = [];
    if (query.area) conditions.push(eq(pressureRecord.area, query.area));
    if (query.pointId) conditions.push(eq(pressureRecord.pointId, query.pointId));
    if (query.inputType) conditions.push(eq(pressureRecord.inputType, query.inputType));
    if (query.startDate) conditions.push(gte(pressureRecord.recordTime, new Date(query.startDate)));
    if (query.endDate) conditions.push(lte(pressureRecord.recordTime, new Date(query.endDate)));

    const whereClause = conditions.length > 0 ? and(...conditions) : undefined;

    const allRecords = await this.db
      .select()
      .from(pressureRecord)
      .where(whereClause)
      .orderBy(desc(pressureRecord.recordTime), asc(pressureRecord.pointId));

    const groupMap = new Map<string, {
      pointId: string;
      area: string;
      date: string;
      timeSlotValues: Record<string, number | null>;
      standardPressure: number;
      recordIds: string[];
      statuses: string[];
      inputType: string;
    }>();

    for (const rec of allRecords) {
      const dateStr = rec.recordTime.toISOString().slice(0, 10);
      const groupKey = `${rec.pointId}|${dateStr}`;

      if (!groupMap.has(groupKey)) {
        groupMap.set(groupKey, {
          pointId: rec.pointId,
          area: rec.area,
          date: dateStr,
          timeSlotValues: {},
          standardPressure: rec.standardPressure,
          recordIds: [],
          statuses: [],
          inputType: rec.inputType,
        });
      }

      const group = groupMap.get(groupKey)!;
      const slot = rec.timeSlot || '默认';
      group.timeSlotValues[slot] = rec.pressureValue;
      group.recordIds.push(rec.id);
      group.statuses.push(rec.status);
    }

    const allGroups = Array.from(groupMap.values());
    const total = allGroups.length;
    const offset = (page - 1) * pageSize;
    const pagedGroups = allGroups.slice(offset, offset + pageSize);

    const items: MergedPressureRow[] = pagedGroups.map((g) => {
      let groupStatus: AuditStatus = 'approved';
      if (g.statuses.some((s: string) => s === 'rejected')) {
        groupStatus = 'rejected';
      } else if (g.statuses.some((s: string) => s === 'pending')) {
        groupStatus = 'pending';
      }

      return {
        pointId: g.pointId,
        area: g.area as AreaType,
        date: g.date,
        timeSlotValues: g.timeSlotValues,
        standardPressure: g.standardPressure,
        recordIds: g.recordIds,
        status: groupStatus,
        inputType: g.inputType as any,
      };
    });

    return { items, total };
  }

  async deleteMergedRow(
    pointId: string,
    date: string,
  ): Promise<{ successCount: number; success: boolean }> {
    const startDate = new Date(`${date}T00:00:00.000Z`);
    const endDate = new Date(`${date}T23:59:59.999Z`);

    const result = await this.db
      .delete(pressureRecord)
      .where(
        and(
          eq(pressureRecord.pointId, pointId),
          gte(pressureRecord.recordTime, startDate),
          lte(pressureRecord.recordTime, endDate),
        ),
      )
      .returning({ id: pressureRecord.id });

    this.logger.log(`Deleted merged row: pointId=${pointId}, date=${date}, count=${result.length}`);
    return { successCount: result.length, success: true };
  }

  async updateMergedRow(
    dto: UpdateMergedRowRequest,
  ): Promise<UpdateMergedRowResponse> {
    const startDate = new Date(`${dto.date}T00:00:00.000Z`);
    const endDate = new Date(`${dto.date}T23:59:59.999Z`);

    const existingRecords = await this.db
      .select()
      .from(pressureRecord)
      .where(
        and(
          eq(pressureRecord.pointId, dto.pointId),
          gte(pressureRecord.recordTime, startDate),
          lte(pressureRecord.recordTime, endDate),
        ),
      );

    let successCount = 0;
    for (const [slot, newValue] of Object.entries(dto.timeSlotValues)) {
      const record = existingRecords.find(
        (r) => (r.timeSlot || '默认') === slot,
      );
      if (!record || newValue == null) continue;

      await this.db
        .update(pressureRecord)
        .set({ pressureValue: newValue, updatedAt: new Date() })
        .where(eq(pressureRecord.id, record.id));
      successCount++;
    }

    this.logger.log(`Updated ${successCount} slots for ${dto.pointId} on ${dto.date}`);
    return { successCount, success: true };
  }

  async batchDeleteMergedRows(
    rows: DeleteMergedRowRequest[],
  ): Promise<{ successCount: number; failCount: number; success: boolean }> {
    let totalDeleted = 0;

    for (const row of rows) {
      const startDate = new Date(`${row.date}T00:00:00.000Z`);
      const endDate = new Date(`${row.date}T23:59:59.999Z`);

      const result = await this.db
        .delete(pressureRecord)
        .where(
          and(
            eq(pressureRecord.pointId, row.pointId),
            gte(pressureRecord.recordTime, startDate),
            lte(pressureRecord.recordTime, endDate),
          ),
        )
        .returning({ id: pressureRecord.id });

      totalDeleted += result.length;
    }

    this.logger.log(`Batch delete merged rows: ${totalDeleted} deleted from ${rows.length} groups`);
    return { successCount: totalDeleted, failCount: 0, success: true };
  }

  async batchRemove(ids: string[]): Promise<{ successCount: number; failCount: number; success: boolean }> {
    if (!ids || ids.length === 0) {
      return { successCount: 0, failCount: 0, success: true };
    }

    const result = await this.db
      .delete(pressureRecord)
      .where(inArray(pressureRecord.id, ids))
      .returning({ id: pressureRecord.id });

    const successCount = result.length;
    const failCount = ids.length - successCount;

    this.logger.log(`Batch delete: ${successCount} succeeded, ${failCount} failed`);
    return { successCount, failCount, success: true };
  }
}
