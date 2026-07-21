# Phase 1：数据源调研报告

**调研日期**: 2026-06-10  
**调研目标**: 确认 CDE 和 NMPA 每个栏目的最优采集方案

---

## 一、核心发现：反爬机制

### 1.1 瑞数 Bot 防护

**CDE** 和 **NMPA** 均使用了 **瑞数信息（RS）Bot 防护** 或类似的 WAF（Web Application Firewall）。

**特征**:
- 首次请求返回 HTTP 202 (CDE) 或 412 (NMPA)
- 加载混淆的 JavaScript 挑战文件
- 随机路径前缀（如 `/4QbVtADbnLVIc/`、`/fpqQrgG7L6po/`）
- 动态生成 Cookie/Token
- 验证失败返回 HTTP 400

**影响**:
- ❌ 普通 HTTP 请求（requests/curl）无法获取数据
- ❌ 默认 Playwright 配置被检测为自动化环境
- ⚠️ 需要反检测措施才能绕过

### 1.2 网络请求分析

```
CDE 指导原则:
  [1] GET /zdyz/index → 202 (Challenge)
  [2] GET /4QbVtADbnLVIc/c.FxJzG50F.6152bb9.js → 200 (JS Challenge)
  [3] GET /zdyz/index → 400 (验证失败)

NMPA 药品法规:
  [1] GET /yaopin/ypfgwj/index.html → 412 (Challenge)
  [2] GET /fpqQrgG7L6po/eaKJbLE9bqof.e17ed02.js → 200 (JS Challenge)
  [3] GET /yaopin/ypfgwj/index.html → 400 (验证失败)
```

---

## 二、栏目分析

### 2.1 CDE 指导原则

| 项目 | 内容 |
|------|------|
| **URL** | https://www.cde.org.cn/zdyz/index |
| **页面类型** | SSR + JS Challenge |
| **公开 API** | ❌ 未发现 |
| **反爬等级** | 🔴 高（瑞数 Bot 防护） |
| **Playwright 必需** | ✅ 是（需反检测配置） |

### 2.2 CDE 征求意见稿

| 项目 | 内容 |
|------|------|
| **URL** | https://www.cde.org.cn/cxk/listpage/9f9c74c73e0f8f56a8bfbc646055026d |
| **页面类型** | SSR + JS Challenge |
| **公开 API** | ❌ 未发现 |
| **反爬等级** | 🔴 高（瑞数 Bot 防护） |
| **Playwright 必需** | ✅ 是（需反检测配置） |

### 2.3 NMPA 药品法规文件

| 项目 | 内容 |
|------|------|
| **URL** | https://www.nmpa.gov.cn/yaopin/ypfgwj/index.html |
| **页面类型** | SSR + JS Challenge |
| **公开 API** | ❌ 未发现（数据查询页面同样有反爬） |
| **反爬等级** | 🔴 高（瑞数 Bot 防护） |
| **Playwright 必需** | ✅ 是（需反检测配置） |

### 2.4 NMPA 药品公告通告

| 项目 | 内容 |
|------|------|
| **URL** | https://www.nmpa.gov.cn/yaopin/ypggtg/index.html |
| **页面类型** | SSR + JS Challenge |
| **公开 API** | ❌ 未发现 |
| **反爬等级** | 🔴 高（瑞数 Bot 防护） |
| **Playwright 必需** | ✅ 是（需反检测配置） |

### 2.5 NMPA 药品政策解读

| 项目 | 内容 |
|------|------|
| **URL** | https://www.nmpa.gov.cn/yaopin/ypzhcjd/index.html |
| **页面类型** | SSR + JS Challenge |
| **公开 API** | ❌ 未发现 |
| **反爬等级** | 🔴 高（瑞数 Bot 防护） |
| **Playwright 必需** | ✅ 是（需反检测配置） |

---

## 三、采集方案对比

### 3.1 方案 A：HTTP 直接请求

**技术方案**:
```python
import requests
response = requests.get(url, headers={"User-Agent": "..."})
```

**可行性**: ❌ **不可行**

**原因**:
- 无法通过 JS Challenge
- 无法生成动态 Cookie
- 返回空页面或 400 错误

**结论**: 完全不可行，放弃此方案。

---

### 3.2 方案 B：第三方数据 API

**可选服务商**:

| 服务商 | 网址 | 数据类型 | 价格 |
|--------|------|----------|------|
| 摩熵数科 | https://open.bcpmdata.com | CDE/NMPA 审评数据 | 付费 |
| 医药魔方 | https://open.pharmcube.com | 药品全生命周期数据 | 付费 |
| 丁香园 | https://open.dxy.cn | 获批药品信息 | 付费 |

**优点**:
- ✅ 数据质量高，结构化好
- ✅ 稳定可靠，无需维护反爬逻辑
- ✅ 合规合法，无法律风险

**缺点**:
- ❌ 需要付费（企业级服务）
- ❌ 数据更新可能有延迟
- ❌ 可能不包含所有栏目（如征求意见稿）

**适用场景**:
- 预算充足的企业项目
- 对数据质量要求极高
- 只需要核心数据（如批准文号、审评状态）

**结论**: 作为备选方案，适合商业项目。

---

### 3.3 方案 C：Playwright + 反检测

**技术方案**:

#### 方案 C1：playwright-stealth

```bash
pip install playwright-stealth
```

```python
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    stealth_sync(page)  # 注入反检测脚本
    page.goto(url)
```

**原理**: 抹去 `navigator.webdriver` 等自动化特征

#### 方案 C2：Patchright

```bash
pip install patchright
```

```python
from patchright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(url)
```

**原理**: 基于 Playwright 改造的反检测浏览器

#### 方案 C3：连接本地浏览器

```bash
# 启动 Chrome（带调试端口）
google-chrome --remote-debugging-port=9222
```

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://localhost:9222")
    page = browser.new_page()
    page.goto(url)
```

**原理**: 使用真实浏览器实例，无自动化特征

**可行性**: ⚠️ **需要测试验证**

**优点**:
- ✅ 可以绕过 JS Challenge
- ✅ 无需付费
- ✅ 可获取完整数据

**缺点**:
- ❌ 需要维护反检测逻辑
- ❌ 可能被升级的反爬机制拦截
- ❌ 需要处理验证码（如有）
- ❌ 采集频率受限

**风险**:
- 瑞数 Bot 防护可能检测到 stealth 模式
- 高频采集可能触发 IP 封禁
- 可能违反网站 ToS（服务条款）

---

## 四、推荐方案

### 4.1 短期方案（POC 验证）

**推荐**: **方案 C1 - playwright-stealth**

**理由**:
1. 实现简单，快速验证可行性
2. 无需额外成本
3. 可以获取完整数据

**实施步骤**:
1. 安装 playwright-stealth
2. 修改 `browser.py` 集成 stealth
3. 测试 5 个栏目是否可通过验证
4. 如果成功，继续开发采集逻辑

### 4.2 中期方案（生产环境）

**推荐**: **方案 C3 - 连接本地浏览器 + 代理池**

**理由**:
1. 最接近真实用户行为
2. 配合代理池可降低封禁风险
3. 可处理验证码（人工或第三方服务）

**实施步骤**:
1. 搭建代理池（或使用付费代理服务）
2. 使用真实 Chrome + 用户数据目录
3. 实现 Cookie 持久化
4. 添加异常处理和重试机制

### 4.3 长期方案（商业化）

**推荐**: **方案 B - 第三方数据 API**

**理由**:
1. 合规合法，无法律风险
2. 数据质量高，维护成本低
3. 适合规模化运营

**实施步骤**:
1. 评估各服务商的数据覆盖范围和价格
2. 签订合作协议
3. 对接 API 接口
4. 建立数据同步机制

---

## 五、下一步行动

### 5.1 立即执行

1. **测试 playwright-stealth**
   ```bash
   cd dazah-backend
   source .venv/bin/activate
   pip install playwright-stealth
   ```

2. **修改 browser.py 集成 stealth**
   ```python
   from playwright_stealth import stealth_sync
   
   # 在 create_page 中添加
   stealth_sync(page)
   ```

3. **运行测试脚本**
   ```bash
   .venv/bin/python scripts/regulatory_poc/network_sniffer.py \
     "https://www.cde.org.cn/zdyz/index" /tmp/test_stealth.json
   ```

### 5.2 验证标准

- [ ] 页面标题不为空
- [ ] 能提取到列表链接
- [ ] 能访问详情页
- [ ] 能提取正文内容

### 5.3 如果 stealth 失败

1. 尝试 Patchright
2. 尝试连接本地浏览器
3. 考虑使用付费代理服务（如 Bright Data）
4. 评估第三方数据 API

---

## 六、附录

### 6.1 相关资源

- **playwright-stealth**: https://github.com/AstreaTech/playwright-stealth
- **Patchright**: https://github.com/AstreaTech/patchright
- **stealth.min.js**: https://github.com/requireCool/stealth.min.js
- **摩熵数科 API**: https://open.bcpmdata.com/api/11.html
- **NMPA 数据查询**: https://www.nmpa.gov.cn/datasearch/home-index.html

### 6.2 法律风险提示

⚠️ **重要**: 爬虫采集可能涉及法律风险，请确保：
1. 遵守 robots.txt 协议
2. 控制采集频率，不影响网站正常运行
3. 不采集个人隐私信息
4. 不用于商业竞争
5. 必要时咨询法律意见

### 6.3 替代方案

如果爬虫方案不可行，可考虑：
1. **RSS 订阅**: 部分栏目可能提供 RSS
2. **邮件订阅**: 官网可能提供更新通知
3. **人工采集**: 对于低频更新的内容
4. **合作获取**: 与官方或第三方建立数据合作

---

**报告编制**: Codex AI Assistant  
**审核状态**: 待验证
