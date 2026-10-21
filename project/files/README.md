# 线上货运代理全流程自动化

> 脱敏展示版：已移除账号信息、委托编号、金额、业务明细、内网地址与本地路径。
> Sanitized showcase: account details, case IDs, amounts, business data, internal hosts, and local paths have been removed.

## English summary

A personal CLI project that automates a document-heavy, multi-institution freight-forwarding workflow in a training system. It attaches to a logged-in Edge browser over CDP, assembles submissions from document metadata, skips completed steps based on the operation log, and supports dry-run previews. Claude Code and Playwright MCP were used as **development tools**; the runtime is deterministic Python + browser automation, with no LLM or OCR.

## 项目背景

货运代理业务涉及发货人、船公司、检验检疫、海关、集装箱堆场等多个机构，单据多、依赖强、顺序严格。在实训系统中，同类业务需要反复点击、反复试错；一旦漏单或提前操作，还会产生“操作失败”记录，影响评分。

这个项目把这些重复操作封装成命令行工具：把“人对流程的理解”和“对单据的查找”固化成可执行的步骤，让同类业务可以按 SOP 复现，而不是每次从头摸索。

## 问题

- 单据类型多，且不同步骤依赖不同单据组合
- 跨机构操作顺序严格，错误操作有成本
- 页面操作重复、反馈分散，难以确认“这一步是否真的完成了”
- 单据内容仍需人工填写，自动化必须明确边界

## 方案

- **接管已登录浏览器**：通过 Playwright 的 CDP 连接已手动登录的 Edge，不保存账号密码
- **文档元数据驱动**：按 `TypeName` 与 `InternalId` 建立单据索引，按步骤需要的类型组装 `docList`；缺少单据时给出明确提示，而不是盲目重试
- **CLI 封装**：`check` / `docs` / `scenes` / `do` / `step` / `log` / `status`，把 12 步出口流程变成可重复执行的命令
- **幂等与核验**：执行前读取操作日志，已完成步骤自动跳过；`dry-run` 只预览不提交
- **人工/自动边界**：程序只提交机构操作，不修改页面上的单据内容；制单仍由人工完成

## 架构

```
单据中心 ──► 按类型索引 ──► 组装 docList ──► 跨机构提交 ──► 操作日志核验
   │              │                │                │              │
   └─ M07/M19/…   └─ TypeName      └─ 缺失提示      └─ 5 类机构    └─ 已完成则跳过
                     + InternalId     + dry-run                       + 可复查
```

- **运行环境**：Python 3 + Playwright Sync
- **连接方式**：CDP（`http://127.0.0.1:<debug-port>`），接管已登录的 Edge
- **交互方式**：在页面上下文调用站点提供的 AJAX 接口，提交机构操作
- **数据**：单据元数据、操作日志；不引入数据库或外部 AI 服务

## 标准流程（出口海运 CY 直单，12 步）

| # | 步骤 | 机构 | 关键单据 |
| --- | --- | --- | --- |
| 1 | 索要单据 | 发货人 | 系统生成合同、发票、装箱单等 |
| 2 | 海运订舱 | 船公司 | M38 + M2A–M2J（十联单） |
| 3 | 出口报检 | 检验检疫 | M07 M19 M21 M04 M17 |
| 4 | 申请用箱 | 船公司 | M2E |
| 5 | 进仓通知 | 发货人 | M13 M10 M11 |
| 6 | 出口报关 | 海关 | M07 M19 M21 M20 M05 M2E M2F M2G |
| 7 | 通知装船 | 堆场 | M2E M2F M2G M2J |
| 8 | 通知装运 | 发货人 | 无（须 ETD 当天之后） |
| 9 | 支付运费 | 船公司 | 无 |
| 10 | 换提单 | 船公司 | M2G（生成 M01 海运提单） |
| 11 | 费用结算 | 发货人 | 无（生成 M78 发票） |
| 12 | 退单 | 发货人 | M78 M2A M01 |

进口海运 CY 直单为 13 步，新增 7 个表单代码（M18、M06、M82、M83、M41、M4A、M4B），使用通用的 `do` 命令执行，未硬编码进 `step`。

## 成果

- **2 单完整跑通到节点 500**：出口海运 CY 直单 1 单、进口海运 CY 直单 1 单
- 出口 SOP 覆盖 **12 步**；进口流程为 **13 步**，新增 **7 个表单代码**
- 覆盖约 **30 类单据**，出口流程涉及 **23 个表单代码**
- 整理出 **57 篇制单指南、37 篇步骤指南、9 条流程视图**的知识库
- 过程中遇到 **2 个阻塞问题**，经交叉核对单据与操作日志，确认由业务系统自身的源数据矛盾导致；通过定位不一致解决，而不是反复重试

## 关键设计

1. **文档元数据驱动**：不靠页面文字猜单据，而是按类型与内部 ID 组装提交内容
2. **日志优先的幂等**：先查最近操作日志，已完成步骤自动跳过；强制重做需要显式参数
3. **安全边界**：只提交业务操作；不修改单据内容；`dry-run` 可预览将要提交的内容
4. **开发与运行分离**：Claude Code、Playwright MCP 用于开发；运行时是确定性 Python 程序，不依赖大模型

## 局限

- 仅出口海运 CY 直单做了完整的 `step` 硬编码；进口流程使用通用 `do`，其他交货方式（DOOR、CFS）与空运、拼单未覆盖
- 单据创建、填写与检查仍需人工完成
- 需要手动登录 Edge，登录失效后没有无人值守的重新登录机制
- 依赖系统日期与 ETD 等业务前置条件
- 没有自动化测试与依赖锁定；结果输出目录未纳入版本管理

## 技术栈

Python 3、Playwright（Sync API）、CDP、Microsoft Edge、ASP.NET AJAX 接口、Markdown/JSON 文档、命令行工具

## 文件

| 文件 | 内容 |
| --- | --- |
| [`SOP-出口海运CY直单.md`](SOP-出口海运CY直单.md) | 脱敏后的 12 步标准作业流程与成功/失败节点 |
| [`simforwarder.py`](simforwarder.py) | 脱敏后的核心代码（CLI、单据组装、流程编排、日志核验） |
| [`case.sample.json`](case.sample.json) | 业务参数示例（占位编号） |

## 使用与声明

- 本项目为个人学习与作品展示，代码和文档归作者所有。
- 请勿将本项目用于绕过平台规则、未经授权的系统或任何实际生产业务。
- 展示版已移除可识别个人、业务与内部环境的信息；如需运行，请自行准备测试环境并替换占位符。
