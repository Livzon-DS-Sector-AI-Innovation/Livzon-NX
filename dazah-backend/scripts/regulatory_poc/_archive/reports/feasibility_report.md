# 法规自动监控可行性报告

生成时间: 2026-06-09 15:07:59

## 测试结果汇总

| 来源 | 栏目 | HTTP状态 | 样例数 | 风险等级 | 技术栈 | 主要问题 |
|------|------|----------|--------|----------|--------|----------|
| NMPA | 法规文件 | 412 | 0 | 中 | Playwright, BeautifulSoup | 未找到列表项，可能需要JS渲染 |
| CDE | 指导原则 | 202 | 0 | 中 | Playwright, BeautifulSoup | 未找到列表项，可能需要JS渲染 |
| CFDI | 公告通告 | 404 | 0 | 中 | Playwright, BeautifulSoup | 未找到列表项，可能需要JS渲染 |
| 国家药典委 | 公告 | 200 | 0 | 中 | Playwright, BeautifulSoup | 页面结构复杂，需进一步适配栏目选择器 |
| 广东省药监局 | 法规文件 | 404 | 0 | 中 | Playwright, BeautifulSoup | 页面结构复杂，需进一步适配栏目选择器 |
| FDA | Guidance Documents | 404 | 0 | 中 | Playwright, BeautifulSoup | FDA页面结构复杂，可能需要调整选择器或使用RSS |
| EMA | Public Consultations | 200 | 0 | 中 | Playwright, BeautifulSoup | EMA页面可能需要调整选择器 |
| EDQM | News & Events | 403 | 0 | 中 | Playwright, BeautifulSoup | EDQM页面可能需要调整选择器 |
| ICH | Guidelines | 200 | 0 | 中 | Playwright, BeautifulSoup | ICH页面可能需要调整选择器 |

## 详细分析

### NMPA - 法规文件

- **测试URL**: https://www.nmpa.gov.cn/xxgk/fgwj/index.html
- **HTTP状态**: 412
- **风险等级**: 中
- **需要JS渲染**: 是
- **需要登录**: 否
- **验证码**: 否
- **附件可下载**: 是
- **推荐技术栈**: Playwright, BeautifulSoup
- **问题**: 未找到列表项，可能需要JS渲染

### CDE - 指导原则

- **测试URL**: https://www.cde.org.cn/main/xxgk/listpage/2de64bb2077a4070b79ae59373755684
- **HTTP状态**: 202
- **风险等级**: 中
- **需要JS渲染**: 是
- **需要登录**: 否
- **验证码**: 否
- **附件可下载**: 是
- **推荐技术栈**: Playwright, BeautifulSoup
- **问题**: 未找到列表项，可能需要JS渲染

### CFDI - 公告通告

- **测试URL**: https://www.nifdc.org.cn/nifdc/bshff/swjgg/index.html
- **HTTP状态**: 404
- **风险等级**: 中
- **需要JS渲染**: 是
- **需要登录**: 否
- **验证码**: 否
- **附件可下载**: 是
- **推荐技术栈**: Playwright, BeautifulSoup
- **问题**: 未找到列表项，可能需要JS渲染

### 国家药典委 - 公告

- **测试URL**: https://www.chp.org.cn
- **HTTP状态**: 200
- **风险等级**: 中
- **需要JS渲染**: 是
- **需要登录**: 否
- **验证码**: 否
- **附件可下载**: 是
- **推荐技术栈**: Playwright, BeautifulSoup
- **问题**: 页面结构复杂，需进一步适配栏目选择器

### 广东省药监局 - 法规文件

- **测试URL**: https://mpa.gd.gov.cn/zwgk/fgwj/index.html
- **HTTP状态**: 404
- **风险等级**: 中
- **需要JS渲染**: 是
- **需要登录**: 否
- **验证码**: 否
- **附件可下载**: 是
- **推荐技术栈**: Playwright, BeautifulSoup
- **问题**: 页面结构复杂，需进一步适配栏目选择器

### FDA - Guidance Documents

- **测试URL**: https://www.fda.gov/drugs/guidance-compliance-regulatory-information/guidances-drugs
- **HTTP状态**: 404
- **风险等级**: 中
- **需要JS渲染**: 是
- **需要登录**: 否
- **验证码**: 否
- **附件可下载**: 是
- **推荐技术栈**: Playwright, BeautifulSoup
- **问题**: FDA页面结构复杂，可能需要调整选择器或使用RSS

### EMA - Public Consultations

- **测试URL**: https://www.ema.europa.eu/en/human-regulatory/overview/public-consultations
- **HTTP状态**: 200
- **风险等级**: 中
- **需要JS渲染**: 是
- **需要登录**: 否
- **验证码**: 否
- **附件可下载**: 是
- **推荐技术栈**: Playwright, BeautifulSoup
- **问题**: EMA页面可能需要调整选择器

### EDQM - News & Events

- **测试URL**: https://www.edqm.eu/en/news-and-events
- **HTTP状态**: 403
- **风险等级**: 中
- **需要JS渲染**: 是
- **需要登录**: 否
- **验证码**: 否
- **附件可下载**: 是
- **推荐技术栈**: Playwright, BeautifulSoup
- **问题**: EDQM页面可能需要调整选择器

### ICH - Guidelines

- **测试URL**: https://www.ich.org/page/guidelines
- **HTTP状态**: 200
- **风险等级**: 中
- **需要JS渲染**: 是
- **需要登录**: 否
- **验证码**: 否
- **附件可下载**: 是
- **推荐技术栈**: Playwright, BeautifulSoup
- **问题**: ICH页面可能需要调整选择器

## 结论与建议

- **低风险（可稳定抓取）**: 0 个来源
- **中风险（需适配）**: 9 个来源
- **高风险（需人工兜底）**: 0 个来源

