# 业务模块目录结构

```text
app/modules/{module}/
├── __init__.py
├── api.py          # HTTP 路由、入参、依赖注入、响应
├── schemas.py      # Pydantic 请求/响应模型
├── models.py       # SQLAlchemy ORM 模型
├── repository.py   # 数据库查询和持久化
├── service.py      # 业务流程、规则校验、事务编排
└── public_api.py   # 可选；提供给其他模块调用的稳定公共接口
```

## 职责规则

- `api.py` 只做 HTTP 层：接收入参、注入依赖、调用 service、返回统一响应。不要写 ORM 查询、复杂业务规则、外部 API 调用或审计落库逻辑。
- `schemas.py` 只描述 API 契约。不要 import ORM model，不承载数据库行为。
- `models.py` 只描述表结构、字段、约束、索引和简单只读属性。不要写业务流程。
- `repository.py` 只负责数据读写。不要决定“是否允许审批”“是否可以删除”等业务语义。
- `service.py` 负责编排业务流程、事务、状态流转、跨表校验、审计和外部集成调用。
- 跨模块调用只能通过对方模块的 `public_api.py`，不要直接 import 其他模块的 `service.py`、`repository.py`、`models.py` 或内部拆分文件。

## 文件拆分规则

当 `service.py`、`models.py`、`schemas.py` 单文件超过约 **300 行**时，拆成同名目录，并在目录级 `__init__.py` re-export 公开对象，保持外部 import 路径稳定。`api.py` 和 `repository.py` 只有确实过大时再按同样规则拆分。
