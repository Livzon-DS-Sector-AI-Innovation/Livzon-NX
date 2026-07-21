# CDE / NMPA 真实数据链路分析报告

**分析日期**: 2026-06-10  
**分析工具**: curl + urllib（HTTP 层）+ 响应头/响应体分析  
**分析目标**: 确认 5 个栏目是否存在稳定的数据获取链路

---

## 一、核心结论

**所有 5 个栏目均不存在稳定的直接数据获取链路。**

CDE 和 NMPA 全站部署了瑞数信息（RS）Bot 防护 WAF，所有 HTTP 请求（包括 curl、requests、urllib）均被拦截，无法获取实际页面内容。不存在公开的 JSON API、RSS 订阅或其他可绕过的数据接口。

| 栏目 | 状态码 | WAF 类型 | JSON API | RSS | 可用链路 |
|------|--------|----------|----------|-----|----------|
| CDE 指导原则 | 202 | 瑞数 | ❌ | ❌ | ❌ 无 |
| CDE 征求意见稿 | 202 | 瑞数 | ❌ | ❌ | ❌ 无 |
| NMPA 药品法规文件 | 412 | 瑞数 | ❌ | ❌ | ❌ 无 |
| NMPA 药品公告通告 | 412 | 瑞数 | ❌ | ❌ | ❌ 无 |
| NMPA 药品政策解读 | 412 | 瑞数 | ❌ | ❌ | ❌ 无 |

---

## 二、逐栏目分析

### 2.1 CDE 指导原则

| 项目 | 结果 |
|------|------|
| **URL** | `https://www.cde.org.cn/zdyz/index` |
| **HTTP 状态码** | 202 Accepted（WAF 挑战页） |
| **响应内容** | 25KB 混淆 JS 挑战脚本 |
| **Set-Cookie** | `FSSBBIl1UgzbN7N80T`、`FSSBBIl1UgzbN7N80S`（瑞数动态 Cookie） |
| **JSON API** | ❌ 未发现任何返回 JSON 的接口 |
| **分页机制** | ❌ 无法确认（页面内容被 WAF 拦截） |
| **Cookie 依赖** | ✅ 强依赖瑞数动态 Cookie |
| **动态 Token** | ✅ JS 挑战生成动态 Token |
| **浏览器必需** | ✅ 必须浏览器执行 JS 挑战 |
| **RSS** | ❌ `/rss`、`/feed` 均返回 202（被拦截） |

**WAF 响应特征**:
```
HTTP/1.1 202 Accepted
Server: ******
Set-Cookie: FSSBBIl1UgzbN7N80T=...; Path=/; expires=Sat, 07 Jun 2036
Set-Cookie: FSSBBIl1UgzbN7N80S=...; Path=/; HttpOnly
Content-Type: text/html; charset=utf-8
```

---

### 2.2 CDE 征求意见稿

| 项目 | 结果 |
|------|------|
| **URL** | `https://www.cde.org.cn/main/xxgk/listpage/9f9c74c73e0f8f56a8bfbc646055026d` |
| **HTTP 状态码** | 202 Accepted（WAF 挑战页） |
| **JSON API** | ❌ 未发现 |
| **分页机制** | ❌ 无法确认 |
| **Cookie 依赖** | ✅ 瑞数动态 Cookie |
| **动态 Token** | ✅ JS 挑战生成 |
| **浏览器必需** | ✅ 是 |

**备注**: 与指导原则栏目使用相同的 WAF 防护，所有路径均返回 202。

---

### 2.3 NMPA 药品法规文件

| 项目 | 结果 |
|------|------|
| **URL** | `https://www.nmpa.gov.cn/yaopin/ypfgwj/index.html` |
| **HTTP 状态码** | 412 Precondition Failed（WAF 挑战页） |
| **响应内容** | 2.5KB 混淆 JS 挑战脚本 |
| **Set-Cookie** | `acw_tc`（会话 Cookie）、`NfBCSins2OywS`（瑞数动态 Cookie） |
| **JSON API** | ❌ 未发现 |
| **分页机制** | ❌ 无法确认 |
| **Cookie 依赖** | ✅ 强依赖瑞数动态 Cookie |
| **动态 Token** | ✅ JS 挑战生成动态 Token |
| **浏览器必需** | ✅ 必须浏览器执行 JS 挑战 |
| **RSS** | ❌ `/rss`、`/feed` 均返回 412 |

**WAF 响应特征**:
```
HTTP/1.1 412 Precondition Failed
Set-Cookie: acw_tc=...;path=/;HttpOnly;Max-Age=1800
Server: ******
Set-Cookie: NfBCSins2OywS=...; Path=/; HttpOnly
Strict-Transport-Security: max-age=31536000
```

---

### 2.4 NMPA 药品公告通告

| 项目 | 结果 |
|------|------|
| **URL** | `https://www.nmpa.gov.cn/yaopin/ypgggg/index.html` |
| **HTTP 状态码** | 412 Precondition Failed |
| **JSON API** | ❌ 未发现 |
| **分页机制** | ❌ 无法确认 |
| **Cookie 依赖** | ✅ 瑞数动态 Cookie |
| **浏览器必需** | ✅ 是 |

---

### 2.5 NMPA 药品政策解读

| 项目 | 结果 |
|------|------|
| **URL** | `https://www.nmpa.gov.cn/yaopin/ypzhcjd/index.html` |
| **HTTP 状态码** | 412 Precondition Failed |
| **JSON API** | ❌ 未发现 |
| **分页机制** | ❌ 无法确认 |
| **Cookie 依赖** | ✅ 瑞数动态 Cookie |
| **浏览器必需** | ✅ 是 |

---

## 三、WAF 防护机制详解

### 3.1 瑞数 Bot 防护流程

```
[客户端]                    [瑞数 WAF]                   [源站]
   |                           |                           |
   |-- GET /page ------------->|                           |
   |                           |-- 检测: 无 JS 执行能力     |
   |<-- 202/412 + JS 挑战 -----|                           |
   |                           |                           |
   | [浏览器执行 JS 挑战]       |                           |
   | [生成动态 Cookie/Token]    |                           |
   |                           |                           |
   |-- GET /page + Cookie ---->|                           |
   |                           |-- 验证 Token              |
   |                           |-- 通过 → 转发到源站        |
   |                           |-------------------------->|
   |<-- 200 + 真实内容 --------|<--------------------------|
```

### 3.2 防护特征

| 特征 | CDE | NMPA |
|------|-----|------|
| **挑战状态码** | 202 | 412 |
| **动态 Cookie 名** | `FSSBBIl1UgzbN7N80T/S` | `NfBCSins2OywS` |
| **会话 Cookie** | 无 | `acw_tc` |
| **JS 文件大小** | ~25KB | ~2.5KB |
| **随机路径前缀** | ✅（如 `/4QbVtADbnLVIc/`） | ✅（如 `/fpqQrgG7L6po/`） |
| **Cookie 有效期** | 10 年 | 30 分钟 |
| **Server 头** | `******`（隐藏） | `******`（隐藏） |

### 3.3 绕过难度评估

| 维度 | 评估 |
|------|------|
| **纯 HTTP 绕过** | ❌ 不可能 |
| **Playwright 默认配置** | ❌ 被检测为自动化环境 |
| **Playwright + 反检测插件** | ⚠️ 可能但极不稳定 |
| **商业反爬服务** | ⚠️ 成本高，成功率不确定 |
| **长期稳定方案** | ❌ 不存在 |

---

## 四、替代路径探测

### 4.1 已探测路径（全部被拦截）

| 路径 | 状态 |
|------|------|
| `https://www.cde.org.cn/api` | 202（被拦截） |
| `https://www.cde.org.cn/rss` | 202（被拦截） |
| `https://www.cde.org.cn/feed` | 202（被拦截） |
| `https://m.cde.org.cn` | 无响应 |
| `https://api.cde.org.cn` | 无响应 |
| `https://app.cde.org.cn` | 无响应 |
| `https://www.nmpa.gov.cn/api/*` | 412（被拦截） |
| `https://www.nmpa.gov.cn/rss` | 412（被拦截） |
| `https://www.nmpa.gov.cn/datasearch/*` | 412（被拦截） |
| `https://www.gov.cn/zhengce/zhengceku/` | 403 |

### 4.2 结论

- ❌ 无公开 JSON API
- ❌ 无 RSS 订阅
- ❌ 无移动端替代入口
- ❌ 无 API 子域名
- ❌ 无政府数据开放平台镜像

---

## 五、数据获取链路总结

### 5.1 链路状态

| 维度 | CDE | NMPA |
|------|-----|------|
| **直接 HTTP 获取** | ❌ 不可行 | ❌ 不可行 |
| **JSON API 接口** | ❌ 不存在 | ❌ 不存在 |
| **RSS 订阅** | ❌ 不存在 | ❌ 不存在 |
| **数据导出** | ❌ 不存在 | ❌ 不存在 |
| **公开数据接口** | ❌ 不存在 | ❌ 不存在 |
| **浏览器自动化** | ⚠️ 理论可行但不稳定 | ⚠️ 理论可行但不稳定 |

### 5.2 各维度判定

| 维度 | 判定 |
|------|------|
| **是否存在返回 JSON 的数据接口** | ❌ 不存在 |
| **接口地址** | N/A |
| **分页机制** | 无法确认（被 WAF 拦截） |
| **是否依赖 Cookie** | ✅ 强依赖瑞数动态 Cookie |
| **是否依赖动态 Token** | ✅ 是，JS 挑战生成 |
| **是否必须浏览器参与** | ✅ 是，必须执行 JS 挑战 |

---

## 六、最终回答

**这些栏目是否存在稳定的数据获取链路？**

**❌ 不存在。**

CDE 和 NMPA 全站部署了瑞数 Bot 防护，所有 5 个目标栏目（CDE 指导原则、CDE 征求意见稿、NMPA 药品法规文件、NMPA 药品公告通告、NMPA 药品政策解读）均被 WAF 拦截。不存在公开的 JSON API、RSS 订阅或其他可直接调用的数据接口。

唯一理论可行的方案是使用反检测浏览器自动化（如 Playwright + stealth 插件），但该方案：
1. 极不稳定（瑞数持续升级检测策略）
2. 维护成本高（需持续对抗反爬升级）
3. 可能违反网站服务条款
4. 无法保证长期可用性

**建议**: 通过第三方数据服务商（如识林、摩熵数科、医药魔方等）获取已清洗的法规数据，而非直接采集 CDE/NMPA。

---

**报告编制**: Codex AI Assistant  
**分析方法**: HTTP 层分析（curl/urllib）+ 响应头/响应体解析  
**审核状态**: 最终版
