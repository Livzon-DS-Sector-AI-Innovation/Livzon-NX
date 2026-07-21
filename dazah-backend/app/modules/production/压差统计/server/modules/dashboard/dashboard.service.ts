import { Injectable, Inject } from '@nestjs/common';
import { DRIZZLE_DATABASE, type PostgresJsDatabase } from '@lark-apaas/fullstack-nestjs-core';
import { count, eq, gte, desc } from 'drizzle-orm';
import { pressureRecord } from '@server/database/schema';
import type { DashboardStats } from '@shared/api.interface';

@Injectable()
export class DashboardService {
  constructor(
    @Inject(DRIZZLE_DATABASE) private readonly db: PostgresJsDatabase,
  ) {}

  async getStats(userContext: any): Promise<DashboardStats> {
    void userContext;

    const todayStart = new Date();
    todayStart.setHours(0, 0, 0, 0);

    const [todayResult] = await this.db
      .select({ count: count() })
      .from(pressureRecord)
      .where(gte(pressureRecord.recordTime, todayStart));

    const [pendingResult] = await this.db
      .select({ count: count() })
      .from(pressureRecord)
      .where(eq(pressureRecord.status, 'pending'));

    const [lastRecord] = await this.db
      .select({ recordTime: pressureRecord.recordTime })
      .from(pressureRecord)
      .orderBy(desc(pressureRecord.recordTime))
      .limit(1);

    return {
      todayCount: Number(todayResult?.count ?? 0),
      pendingCount: Number(pendingResult?.count ?? 0),
      lastRecordTime: lastRecord?.recordTime
        ? lastRecord.recordTime.toISOString()
        : null,
    };
  }
}
