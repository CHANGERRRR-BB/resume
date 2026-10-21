# 出口海运 CY 直单 · 标准作业流程（SOP）

> 适用：SimForwarder 出口海运、CY 交货、直单（非拼单）、发货人自拉自送。
> 目标：下一次同类业务按本文件直接执行，不再重复试错。
> 展示版说明：已移除站点地址、委托编号、金额与业务基准数据。

---

## 一、环境要求与启动

| 项目 | 要求 |
|---|---|
| 站点 | `http://<training-host>/simforwarder/` |
| 浏览器 | Edge，持久化配置目录 `<project-root>/.browser-profile` |
| 调试端口 | 9222（Playwright 通过 CDP 接管） |
| Python | 已安装 playwright（`pip show playwright` 可查） |

启动 Edge（保持窗口打开）：

```bat
"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --remote-debugging-port=9222 --user-data-dir="<project-root>/.browser-profile"
```

若页面跳到 `Login.aspx`，在 Edge 中手动登录一次，然后停在 `Student/Home.aspx`。

自检：

```bat
python simforwarder.py check
```

---

## 二、业务开始前要记录的数据

办理前先把这些值记下来，后续单据和命令都依赖它们：

| 数据 | 说明 |
|---|---|
| 委托编号 | 如 `<case-id>`，填入 `case.json` |
| 装期（ETD） | **通知装运必须等到这一天** |
| 最迟装运日 | 不得超过 |
| 船名/航次、箱号/箱型 | 订舱后取得 |
| 货物、件数、重量、体积、货值 | 制单用 |
| 报价与成本 | 报价 = 成本 + 利润，按业务实际填写 |

`case.json` 示例（每次只改 `commissionId`）：

```json
{ "commissionId": "<case-id>", "companyRoleType": 1 }
```

---

## 三、标准流程总表

> 机构 ID：1 船公司、3 检验检疫、5 发货人、7 集装箱堆场、9 海关。
> “成功节点”是流程推进后的场景号，返回其他节点按“失败处理”章节排查。

| # | 步骤 | 机构 | commandId | 提交单据 | 成功节点 |
|---|---|---|---|---|---|
| 1 | 索要单据 | 5 发货人 | 501 | 无 | 100 |
| 2 | 海运订舱 | 1 船公司 | 101 | M38 + M2A～M2J（十联单） | 100 |
| 3 | 出口报检 | 3 检验检疫 | 301 | M07 M19 M21 M04 M17（信用证如有） | 100 |
| 4 | 申请用箱 | 1 船公司 | 103 | M2E（10-5） | 200 |
| 5 | 进仓通知 | 5 发货人 | 502 | M13 M10 M11 | 200 |
| 6 | 出口报关 | 9 海关 | 901 | M07 M19 M21 M20 M05 M2E M2F M2G | 100 |
| 7 | 通知装船 | 7 堆场 | 702 | M2E M2F M2G M2J | 200 |
| 8 | 通知装运 | 5 发货人 | 503 | 无（**须 ETD 当天之后**） | 300 |
| 9 | 支付运费 | 1 船公司 | 104 | 无 | 300 |
| 10 | 换提单 | 1 船公司 | 105 | M2G（成功生成 M01 海运提单） | 400 |
| 11 | 费用结算 | 5 发货人 | 504 | 无（成功生成 M78 发票） | 400 |
| 12 | 退单 | 5 发货人 | 505 | M78 M2A M01（检验证书如有） | 500 |

---

## 四、命令执行

所有命令在本目录（`project/files`，即 `simforwarder.py` 与 `case.json` 所在目录）下运行：

```bat
REM 查看当前委托的所有单据及 InternalId
python simforwarder.py docs

REM 查看 12 个标准步骤的完成情况
python simforwarder.py status

REM 按顺序执行业务步骤（单据由程序自动按类型组装）
python simforwarder.py step get-docs
python simforwarder.py step booking
python simforwarder.py step inspection
python simforwarder.py step apply-container
python simforwarder.py step warehouse-notice
python simforwarder.py step customs
python simforwarder.py step load-ship
python simforwarder.py step notify-shipment
python simforwarder.py step pay-freight
python simforwarder.py step get-bl
python simforwarder.py step settle
python simforwarder.py step return-docs

REM 查看操作日志（确认已完成步骤）
python simforwarder.py log --pages 2
```

其他辅助命令：

```bat
REM 查看某机构可办理的业务及 commandId
python simforwarder.py scenes 5
python simforwarder.py scenes 1 --all

REM 临时调用任意操作（单据可手写 docList）
python simforwarder.py do 5 503
python simforwarder.py do 1 105 --doc-types M2G
```

**执行前检查**：

- `step` 会先查操作日志（最近 7 天、3 页），已完成步骤自动跳过；确需重做时加 `--force`。若业务跨期较长，先用 `log --pages 5` 确认。
- `step` 会先列出将要提交的单据。若提示“缺少单据类型”，按提示先在“单据管理”中生成并填写对应单据，再重新执行。
- 不确定进度时，先运行 `python simforwarder.py log --pages 2`。

---

## 五、需要人工制单的前置步骤

程序只负责“机构操作”（提交单据、推进流程），以下单据必须先做好：

| 时机 | 人工操作 |
|---|---|
| 订舱前 | 单据管理 → 新增 **(10-1) 集装箱货物托运单**，填写并检查；保存后系统自动生成其余九联（M2B～M2J）。同时生成/填写 M38 集装箱预配清单。 |
| 报检前 | 新增 **M17 出境货物检验检疫申请**，填写并检查；M04 代理报检委托书由发货人提供。 |
| 报关前 | 打开“国际贸易单一窗口”，创建 **M05 出口货物报关单**，填写 → 上载 → 申报 → 打印。打印按钮为 `#sp_daying`；打印前 `CustomEntry.GetRecord` 的 `N0172` 必须为 4。 |

其余单据由系统自动生成：

- 索要单据 → M07 合同、M19 商业发票、M21 装箱单、M20 代理报关委托书、M04 代理报检委托书
- 订舱 → M38、M2A～M2J、M16 订舱确认书
- 用箱 → M10/M11 设备交接单
- 进仓通知 → M13 进仓通知单
- 换提单 → M01 海运提单
- 费用结算 → M78 国际货物代理运输专业发票

---

## 六、成功/失败节点速查

| 步骤 | 成功 | 常见失败节点与含义 |
|---|---|---|
| 索要单据 | 100 | 101 单据问题；102 业务类型不符 |
| 订舱 | 100 | 101 单据有误；102 重试；103 资料不全 |
| 出口报检 | 100 | 101 单据有误；102 重试；103 资料不全 |
| 申请用箱 | 200 | 201 单据拿错；202 资金/资料问题 |
| 进仓通知 | 200 | 202 单据需修改 |
| 出口报关 | 100 | 101 单据有误；102 待确认；110 未报检 |
| 通知装船 | 200 | 202 未报关；205 已开船（只能改船期） |
| 通知装运 | 300 | **301 货物尚未装运（未到 ETD）**；303 已经通知过 |
| 支付运费 | 300 | 301 业务不符；304 未装运 |
| 换提单 | 400 | 401 单据拿错；403 未付运费；406 未装船 |
| 费用结算 | 400 | 401 单据拿错；404 未出运 |
| 退单 | 500 | 501 单据拿错；502 未先结算 |

特殊返回：

- `Code 9001 系统异常` → 检查请求中的 `InstitutionId` / `CommissionId` 是否为明确值（本程序已固定传明确值）。
- `重复费用结算` / `重复退单` 等 → 该业务步骤已经完成，不要再次操作；会新增一次“操作失败”。
- 页面残留弹窗挡住操作 → 关闭 `DocumentCenter.aspx` 弹窗后重试。

---

## 七、关键规则与单据状态变化

1. **通知装运的时间限制**：必须等系统日期 ≥ ETD。提前操作会记一次“操作失败”，影响业务能力评分。
2. **不要用“申请修改船期”绕过日期**：会产生费用，且属于错误业务操作。
3. **通知装船后**：M2E（10-5）、M2F（10-6）被堆场收走，单据列表中消失，属正常。
4. **换提单后**：M2G（10-7）被船公司收走，生成 M01 海运提单。
5. **退单后**：M2A、M01 被发货人收走；M78 保留在货代单据列表中。
6. **滞箱费**：集装箱使用超过 7 天，支付运费时会产生滞箱费；CY 自拉自送没有拖车费。
7. **拼单不适用本 SOP**：拼单需要主单/分单分别处理十联单，另见专门流程。

---

## 八、评分注意事项

系统按 **使用情况、报价能力、盈利能力、制单能力、业务能力** 评分，学生端只显示公司总分，不显示明细。

从本次业务总结出的可避免失分点：

| 失分点 | 如何避免 |
|---|---|
| 报检时“单据填写有误” | 提交前用单据检查功能逐张检查，尤其 M17、M04 |
| 未到船期就点“通知装运” | 等 ETD 当天再执行 `step notify-shipment` |
| 业务完成后重复结算/退单 | 用 `step`（自动查日志跳过）或先看 `log`；不要手动重复点击 |
| 托运单/报关委托书检查有警告 | 填写后查看警告项（如 M2A30/M2A33/M2A37）并修正 |

另外：

- 报价成功率按“成功/失败”计，按实际成功/失败次数统计。
- 利润 = 收入 − 支出；报价前先做成本预算，按业务实际填写。
- 全部完成后，在“我的公司 → 公司成员”把公司可分配分数分配给成员。

---

