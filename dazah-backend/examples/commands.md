# 常用命令

## 数据库迁移

```bash
uv run alembic revision --autogenerate -m "describe change"
uv run alembic upgrade head
uv run alembic downgrade -1
```

## 代码验证

完成代码修改后至少运行：

```bash
uv run ruff check .
uv run mypy app tests
uv run pytest
```

## 迁移验证

如果修改了 Alembic：

```bash
uv run alembic heads
```

## 应用启动验证

如果修改了应用启动、路由或依赖注入：

```bash
uv run python -c "from app.main import app; print(app.title)"
```
