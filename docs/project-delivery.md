# GeoExplore 本地演示指南

## 演示前准备

按[本地启动说明](02-getting-started.md)创建环境。自行取得允许使用的六份 PDF，依照[语料说明](../data/README.md)核对 manifest 哈希与语料身份；仓库未附 PDF。真实生成需要本机 `.env` 中有效的 Provider 配置。不要将密钥或代理凭据放进演示材料。

在两个终端分别启动 `app.asgi:app`（127.0.0.1:9101）和 Vite（127.0.0.1:5180）。演示边界是本机原型，浏览器 client ID 不提供用户认证。没有 PDF 或真实 Provider 时，可展示代码结构与离线测试，不能替代为真实语料生成演示。

## 一次固定问题演示

1. 在页面选定文档 `geo-of12-1191`，确认相关 metadata filters 与问题范围一致。
2. 提问：该报告的 P 波折射调查使用多少个检波器、检波器频率和间距分别是多少？
3. 等待最终状态，记录实际答案、引用文档、chunk ID 和物理 PDF 页码。
4. 对照本机 PDF 人工检查数值、单位及引用是否直接支持回答；如返回证据不足，原样记录。

历史 `geo-gen-accept-003` 的对照事实为 96 个 40-Hertz compressional-wave geophones、间距 6 ft，对应 `geo-of12-1191_36`、物理 PDF 第 8 页。这些是历史对照，不能预先写成新一次浏览器演示的观测结果。页面能够打开、API 健康、JSON/SSE 返回正常也分别不能证明答案正确。

## 如何解释结果

Acceptance 的状态匹配为 8/10，原验收门槛未通过；6/8 正确且完整属于历史人工汇总，原 JSON 仍保留 PDF 人工复核待完成标记。Day 3 的八题同语料结果单独报告，不能与 Acceptance 合并。详细分母和失败案例见[评测摘要](evaluation-summary.md)。

本仓库不提供可复核的浏览器截图包，也不声称本次发布准备已完成浏览器 E2E。若另行开展演示，将新的本机记录放在忽略的 `output/` 下，并在公开前去除个人路径、会话身份和凭据。新生成运行需先按[协议](evaluation-protocol.md)核对输入与输出路径。

## 代码与证据入口

- [架构](ARCHITECTURE.md)：从前端到 BM25、生成、引用和持久化的路径。
- [评测题集与实现](../evals/README.md)：各 schema 与评分器用途。
- [历史证据索引](../evals/results/README.md)：两次 Acceptance 和完整 Day 3 证据包。
- [发布范围](release-scope.md)：来源、许可、实验边界与已知限制。
