import {
  Controller,
  Get,
  Post,
  Put,
  Delete,
  Param,
  Query,
  Body,
} from '@nestjs/common';
import { NeedLogin, CanRole } from '@lark-apaas/fullstack-nestjs-core';
import { PointMappingsService } from './point-mappings.service';
import type {
  PaginatedResponse,
  PointMapping,
  CreatePointMappingRequest,
  PointMappingQuery,
  CheckUniqueResponse,
} from '@shared/api.interface';

@Controller('api/point-mappings')
export class PointMappingsController {
  constructor(private readonly pointMappingsService: PointMappingsService) {}

  @Get()
  async list(
    @Query('area') area?: string,
    @Query('keyword') keyword?: string,
    @Query('page') page?: string,
    @Query('pageSize') pageSize?: string,
  ): Promise<PaginatedResponse<PointMapping>> {
    const query: PointMappingQuery = {
      area: area as any,
      keyword,
      page: page ? parseInt(page, 10) : 1,
      pageSize: pageSize ? parseInt(pageSize, 10) : 50,
    };
    return this.pointMappingsService.list(query);
  }

  @Get('check-unique')
  async checkUnique(@Query('pointId') pointId: string): Promise<CheckUniqueResponse> {
    return this.pointMappingsService.checkUnique(pointId);
  }

  @Post()
  @NeedLogin()
  @CanRole(['admin'])
  async create(@Body() dto: CreatePointMappingRequest): Promise<{ id: string; success: boolean }> {
    return this.pointMappingsService.create(dto);
  }

  @Put(':id')
  @NeedLogin()
  @CanRole(['admin'])
  async update(
    @Param('id') id: string,
    @Body() dto: CreatePointMappingRequest,
  ): Promise<{ success: boolean }> {
    return this.pointMappingsService.update(id, dto);
  }

  @Delete(':id')
  @NeedLogin()
  @CanRole(['admin'])
  async delete(@Param('id') id: string): Promise<{ success: boolean }> {
    return this.pointMappingsService.delete(id);
  }
}
