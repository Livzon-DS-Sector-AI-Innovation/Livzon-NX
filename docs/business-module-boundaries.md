# Dazah 业务归属与跨模块开发边界

本文件用于决定新需求应由哪个后端模块承接。模块代码、数据库 schema 和 Agent
Provider 的当前清单以 `dazah-backend/app/shared/module_registry.py` 为准；这里说明
业务数据和规则的归属，不复制接口或表清单。

## 先确定记录所有者

| 所有者 | 承接的业务记录和规则 |
| --- | --- |
| `production` | 批次、工序、生产记录、产量及生产计划的执行数据。 |
| `product` | 产品基础档案、规格等产品主数据及其同步。 |
| `equipment` | 设备台账、维修、保养、巡检及设备备件业务。 |
| `safety` | 隐患、风险、特殊作业和安全检查。 |
| `environment` | 环保监测、排放、设施运行和环保台账。 |
| `energy` | 能源来源、采集、计量、指标和能耗分析。 |
| `warehouse` | 库存、库位、出入库及仓储同步状态。 |
| `procurement` | 采购需求、供应商、询价、订单和到货协同。 |
| `administration` | 行政事务、资产、后勤和公共服务事项。 |
| `hr` | 员工、岗位、入离职、培训和考勤。 |
| `research` | 研发项目、试验批、处方工艺和研发记录。 |
| `registration` | 注册项目、申报进度、资料管理和注册事务流程。 |
| `regulatory_tracker` | 法规来源、采集任务、法规文档及跟踪状态。 |
| `dossier_writer` | 申报资料章节、模板、素材及辅助撰写过程。 |
| `quality` | 偏差、CAPA、检验、放行、变更和质量体系记录。 |

相邻业务按**记录的最终写入与状态解释责任**区分：产品规格由 `product` 维护，
批次执行由 `production` 维护，库存数量由 `warehouse` 维护；注册项目进度属于
`registration`，法规采集属于 `regulatory_tracker`，资料章节与素材属于
`dossier_writer`。一个页面同时展示这些数据，不改变各记录的所有者。

## 平台和编排层

- `app/core/` 管数据库、配置、响应、异常和统一 LLM 客户端等技术设施，不保存
  某个业务模块的流程规则。
- `app/platform/identity/` 管用户、可信身份、权限和数据范围；
  `app/platform/audit/` 管通用审计；`app/platform/integrations/feishu/` 管
  无业务归属的协议和客户端。业务飞书配置、映射、同步规则及同步状态留在所属模块。
- `app/modules/agent/` 管 Agent 工具目录、权限、确认、执行和审计链路。
  业务工具由记录所有者模块声明，handler 调用该模块 Service。
- `Hermes-Lite/` 管 Agent 运行与飞书 Gateway。Dazah 业务数据和动作只经
  `dazah_tool` 进入后端工具网关；飞书原生资源走 `lark_cli`。
- 前端路由可以组合多个所有者的只读数据；写操作仍调用该记录所有者的 API。
  身份、审计等共享能力调用其公开平台 API。

## 新需求的落点

1. 先找谁创建记录、维护状态机、审批责任和数据约束；该模块的 Service 承接规则，
   Repository/Model 承接持久化，API/Schema 提供对外契约。不要按页面菜单位置
   或当前调用方决定归属。
2. 别的模块需要这些数据时，先用所有者的 `public_api.py` 或已有公开契约；不得
   导入其 repository、内部 service、handler、配置表或私有模型。跨模块写入由
   所有者 Service 执行，调用方不得直接改对方表。
3. 一个流程跨多个所有者时，明确发起方、每一步的权限和事务边界、失败后可见
   状态及审计责任，再实现调用或事件；不能靠跨模块 ORM 操作假定整体原子性。
4. 只有无业务归属且至少有明确跨模块调用方的协议能力才下沉到 `platform/`；
   通用技术能力进入 `core/`，轻量共享契约进入 `shared/`。修改公共层时检查
   所有调用方。
5. 新增模块时更新 `module_registry.py` 的模块与 schema 声明、路由装配、
   migration 和受影响测试；需要 Agent 能力才声明 `agent_tools_module`。
   端点或 Schema 改动按根规范运行 `scripts/generate-api.ps1`。

现有飞书只读镜像及部分跨模块直接导入尚未满足上述边界。修改这些路径时先核对
调用关系并逐步迁移，不把历史耦合复制到新功能。
