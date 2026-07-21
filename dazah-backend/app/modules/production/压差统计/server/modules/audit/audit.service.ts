import { Injectable, Inject, Logger } from '@nestjs/common';
import { DRIZZLE_DATABASE, type PostgresJsDatabase } from '@lark-apaas/fullstack-nestjs-core';
import { pressureRecord } from '@server/database/schema';
import { count, eq, and, gte, desc } from 'drizzle-orm';
import type { AuditStats, PaginatedResponse, AuditRecordItem } from '@shared/api.interface';

@Injectable()
export class AuditService {
  private readonly logger = new Logger(AuditService.name);

  constructor(
    @Inject(DRIZZLE_DATABASE) private readonly db: PostgresJsDatabase,
  ) {}

  async getStats(): Promise<AuditStats> {
    const todayStart = new Date();
    todayStart.setHours(0, 0, 0, 0);

    const [pendingResult, todayApprovedResult, rejectedResult] = await Promise.all([
      this.db
        .select({ count: count() })
        .from(pressureRecord)
        .where(eq(pressureRecord.status, 'pending')),
      this.db
        .select({ count: count() })
        .from(pressureRecord)
        .where(
          and(
            eq(pressureRecord.status, 'approved'),
            gte(pressureRecord.updatedAt, todayStart),
          ),
        ),
      this.db
        .select({ count: count() })
        .from(pressureRecord)
        .where(eq(pressureRecord.status, 'rejected')),
    ]);

    return {
      pendingCount: Number(pendingResult[0]?.count ?? 0),
      todayApprovedCount: Number(todayApprovedResult[0]?.count ?? 0),
      rejectedCount: Number(rejectedResult[0]?.count ?? 0),
    };
  }

  async getPendingRecords(
    page: number,
    pageSize: number,
  ): Promise<PaginatedResponse<AuditRecordItem>> {
    const offset = (page - 1) * pageSize;

    const [items, totalResult] = await Promise.all([
      this.db
        .select({
          id: pressureRecord.id,
          pointId: pressureRecord.pointId,
          area: pressureRecord.area,
          pressureValue: pressureRecord.pressureValue,
          standardPressure: pressureRecord.standardPressure,
          recordTime: pressureRecord.recordTime,
          inputType: pressureRecord.inputType,
          creator: pressureRecord.creator,
        })
        .from(pressureRecord)
        .where(eq(pressureRecord.status, 'pending'))
        .orderBy(desc(pressureRecord.recordTime))
        .limit(pageSize)
        .offset(offset),
      this.db
        .select({ count: count() })
        .from(pressureRecord)
        .where(eq(pressureRecord.status, 'pending')),
    ]);

    const total = Number(totalResult[0]?.count ?? 0);

    const mappedItems: AuditRecordItem[] = items.map((item) => ({
      id: item.id,
      pointId: item.pointId,
      area: item.area as AuditRecordItem['area'],
      pressureValue: item.pressureValue,
      standardPressure: item.standardPressure,
      recordTime: item.recordTime.toISOString(),
      inputType: item.inputType as AuditRecordItem['inputType'],
      creator: item.creator,
    }));

    this.logger.log(`getPendingRecords: page=${page}, pageSize=${pageSize}, total=${total}`);

    return { items: mappedItems, total };
  }
}
