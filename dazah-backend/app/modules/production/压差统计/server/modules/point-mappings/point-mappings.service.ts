import { Injectable, Inject, NotFoundException, Logger } from '@nestjs/common';
import { DRIZZLE_DATABASE, type PostgresJsDatabase } from '@lark-apaas/fullstack-nestjs-core';
import { pointMapping } from '@server/database/schema';
import { eq, and, like, count, desc } from 'drizzle-orm';
import type {
  PaginatedResponse,
  PointMapping,
  CreatePointMappingRequest,
  PointMappingQuery,
  CheckUniqueResponse,
} from '@shared/api.interface';

@Injectable()
export class PointMappingsService {
  private readonly logger = new Logger(PointMappingsService.name);

  constructor(
    @Inject(DRIZZLE_DATABASE) private readonly db: PostgresJsDatabase,
  ) {}

  async list(query: PointMappingQuery): Promise<PaginatedResponse<PointMapping>> {
    const page = query.page ?? 1;
    const pageSize = query.pageSize ?? 50;
    const offset = (page - 1) * pageSize;

    const conditions = [];
    if (query.area) conditions.push(eq(pointMapping.area, query.area));
    if (query.keyword) conditions.push(like(pointMapping.pointId, `%${query.keyword}%`));

    const whereClause = conditions.length > 0 ? and(...conditions) : undefined;

    const [items, totalResult] = await Promise.all([
      this.db
        .select()
        .from(pointMapping)
        .where(whereClause)
        .orderBy(pointMapping.pointId)
        .limit(pageSize)
        .offset(offset),
      this.db
        .select({ count: count() })
        .from(pointMapping)
        .where(whereClause),
    ]);

    const total = Number(totalResult[0]?.count ?? 0);

    const mappedItems: PointMapping[] = items.map((item) => ({
      id: item.id,
      pointId: item.pointId,
      area: item.area as PointMapping['area'],
      standardPressure: item.standardPressure,
    }));

    return { items: mappedItems, total };
  }

  async getAll(): Promise<PointMapping[]> {
    const items = await this.db.select().from(pointMapping).orderBy(pointMapping.pointId);
    return items.map((item) => ({
      id: item.id,
      pointId: item.pointId,
      area: item.area as PointMapping['area'],
      standardPressure: item.standardPressure,
    }));
  }

  async findByPointId(pointId: string): Promise<PointMapping | null> {
    const rows = await this.db
      .select()
      .from(pointMapping)
      .where(eq(pointMapping.pointId, pointId))
      .limit(1);

    if (rows.length === 0) return null;

    const item = rows[0];
    return {
      id: item.id,
      pointId: item.pointId,
      area: item.area as PointMapping['area'],
      standardPressure: item.standardPressure,
    };
  }

  async checkUnique(pointId: string): Promise<CheckUniqueResponse> {
    const rows = await this.db
      .select({ id: pointMapping.id })
      .from(pointMapping)
      .where(eq(pointMapping.pointId, pointId))
      .limit(1);

    return { exists: rows.length > 0 };
  }

  async create(dto: CreatePointMappingRequest): Promise<{ id: string; success: boolean }> {
    const existing = await this.checkUnique(dto.pointId);
    if (existing.exists) {
      throw new Error('该编号已存在');
    }

    const result = await this.db
      .insert(pointMapping)
      .values({
        pointId: dto.pointId,
        area: dto.area,
        standardPressure: dto.standardPressure,
      })
      .returning({ id: pointMapping.id });

    this.logger.log(`Created point mapping: ${dto.pointId}`);
    return { id: result[0]?.id ?? '', success: true };
  }

  async update(id: string, dto: CreatePointMappingRequest): Promise<{ success: boolean }> {
    const result = await this.db
      .update(pointMapping)
      .set({
        pointId: dto.pointId,
        area: dto.area,
        standardPressure: dto.standardPressure,
        updatedAt: new Date(),
      })
      .where(eq(pointMapping.id, id))
      .returning({ id: pointMapping.id });

    if (result.length === 0) {
      throw new NotFoundException('位点不存在');
    }

    this.logger.log(`Updated point mapping: ${dto.pointId}`);
    return { success: true };
  }

  async delete(id: string): Promise<{ success: boolean }> {
    const result = await this.db
      .delete(pointMapping)
      .where(eq(pointMapping.id, id))
      .returning({ id: pointMapping.id });

    if (result.length === 0) {
      throw new NotFoundException('位点不存在');
    }

    this.logger.log(`Deleted point mapping: ${id}`);
    return { success: true };
  }
}
