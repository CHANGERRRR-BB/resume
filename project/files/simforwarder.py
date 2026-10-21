# -*- coding: utf-8 -*-
"""SimForwarder 自动化助手（脱敏展示版）

展示版说明：内部站点地址已替换为 <training-host>，业务数据与本地路径已移除。
通过 CDP 接管已登录的 Edge，直接调用站点后端 AJAX 接口完成业务操作。
适用于：出口海运 CY 直单（发货人自拉自送）。

用法：
    python simforwarder.py check
    python simforwarder.py docs
    python simforwarder.py scenes 5
    python simforwarder.py step get-docs
    python simforwarder.py do 5 503
    python simforwarder.py do 1 105 --doc-types M2G
    python simforwarder.py log

委托号默认读取 case.json，可用 --commission 覆盖。
"""
import argparse
import json
import os
import sys

BROWSER = None  # 延迟导入 playwright，避免 check 之外无谓依赖

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

CDP_URL = "http://127.0.0.1:9222"
BASE = "http://<training-host>/simforwarder"
HOME_URL = BASE + "/Student/Home.aspx"
SCENARIO_URL = (BASE + "/Student/Institution/Scenario.aspx"
                "?commissionId={cid}&institutionId={inst}&companyRoleType={role}")
DOC_CENTER_URL = BASE + "/Student/DocumentCenter.aspx?wayBillId={cid}&documentCenterType=1"
LOG_URL = BASE + "/Student/OperationLog.aspx"

HERE = os.path.dirname(os.path.abspath(__file__))
CASE_FILE = os.path.join(HERE, "case.json")

# 出口海运 CY 直单的标准步骤：name -> (机构ID, commandId, 需要提交的单据类型)
STEPS = {
    "get-docs":        (5, "501", []),
    "booking":         (1, "101", ["M38", "M2A", "M2B", "M2C", "M2D",
                                   "M2E", "M2F", "M2G", "M2H", "M2I", "M2J"]),
    "inspection":      (3, "301", ["M07", "M19", "M21", "M04", "M17"]),
    "apply-container": (1, "103", ["M2E"]),
    "warehouse-notice": (5, "502", ["M13", "M10", "M11"]),
    "customs":         (9, "901", ["M07", "M19", "M21", "M20", "M05",
                                   "M2E", "M2F", "M2G"]),
    "load-ship":       (7, "702", ["M2E", "M2F", "M2G", "M2J"]),
    "notify-shipment": (5, "503", []),
    "pay-freight":     (1, "104", []),
    "get-bl":          (1, "105", ["M2G"]),
    "settle":          (5, "504", []),
    "return-docs":     (5, "505", ["M78", "M2A", "M01"]),
}

STEP_TITLES = {
    "get-docs": "索要单据（发货人）",
    "booking": "海运订舱（船公司）",
    "inspection": "出口报检（海关检验检疫）",
    "apply-container": "申请用箱（船公司）",
    "warehouse-notice": "进仓通知（发货人）",
    "customs": "出口报关（海关）",
    "load-ship": "通知装船（集装箱堆场）",
    "notify-shipment": "通知装运（发货人）",
    "pay-freight": "支付运费（船公司）",
    "get-bl": "换提单（船公司）",
    "settle": "费用结算（发货人）",
    "return-docs": "退单（发货人）",
}

MISSING_HINTS = {
    "booking": "请先在“单据管理”中新增并填写 (10-1) 集装箱货物托运单，系统会自动生成十联单。",
    "inspection": "请先新增、填写并检查“出境货物检验检疫申请”(M17)，以及代理报检委托书(M04)。",
    "customs": "请先在“国际贸易单一窗口”完成出口货物报关单(M05)的预录入、上载、申报和打印。",
    "return-docs": "退单需要货代发票(M78)、托运单(M2A)和海运提单(M01)，缺一不可。",
}

# 操作日志中代表“该步骤已完成”的成功记录
STEP_DONE_PATTERNS = {
    "get-docs": "成功索要单据",
    "booking": "成功订舱",
    "inspection": "成功办理出口报检",
    "apply-container": "成功申请用箱",
    "warehouse-notice": "成功通知进仓",
    "customs": "成功办理出口报关",
    "load-ship": "成功安排装船",
    "notify-shipment": "成功通知装运",
    "pay-freight": "成功向船公司结算运费",
    "get-bl": "成功向船公司换提单",
    "settle": "成功费用结算",
    "return-docs": "成功退单给发货人",
}


# ---------------------------------------------------------------- browser --
def get_browser():
    global BROWSER
    if BROWSER is None:
        from playwright.sync_api import sync_playwright
        BROWSER = sync_playwright().start()
    return BROWSER


def connect():
    b = get_browser().chromium.connect_over_cdp(CDP_URL, timeout=10000)
    if not b.contexts:
        raise SystemExit("CDP 已连接，但浏览器没有上下文。")
    return b.contexts[0]


def open_page(ctx, url, wait_js="typeof AjaxHelper !== 'undefined'"):
    pg = ctx.new_page()
    pg.on("dialog", lambda d: d.accept())
    pg.goto(url, wait_until="domcontentloaded", timeout=30000)
    pg.wait_for_function(wait_js, timeout=20000)
    pg.wait_for_timeout(500)
    if "Login.aspx" in pg.url:
        pg.close()
        raise SystemExit("登录状态已失效，请在 Edge 中手动登录后重试。")
    return pg


# ------------------------------------------------------------------ helpers --
def load_case(args):
    cid = getattr(args, "commission", None)
    role = 1
    if not cid and os.path.exists(CASE_FILE):
        with open(CASE_FILE, encoding="utf-8") as f:
            case = json.load(f)
        cid = case.get("commissionId")
        role = case.get("companyRoleType", 1)
    if not cid:
        raise SystemExit("缺少委托号：请创建 case.json 或使用 --commission 指定。")
    return cid, role


JS_GET_DOCS = """(cid) => new Promise(resolve => {
    AjaxHelper.send("Certificate.GetCertificatesByCommission",
        { wayBillId: cid }, resolve);
})"""

JS_GET_NODE = """(id) => {
    if (typeof _scenariosHash === 'undefined') return null;
    const v = _scenariosHash.get(String(id));
    if (!v) return null;
    return (v.RoleScenarioContents || []).map(x => x.Content).join(' | ');
}"""


def fetch_docs(pg, cid):
    result = pg.evaluate(JS_GET_DOCS, cid)
    if not result or result.get("Code") != 0:
        raise SystemExit(f"获取单据列表失败：{result}")
    return result.get("Value") or []


def build_doc_list(docs, types, cid):
    by_type = {}
    for d in docs:
        by_type.setdefault(d.get("TypeName"), []).append(d)
    missing = [t for t in types if t not in by_type]
    if missing:
        return None, missing
    parts = []
    for t in types:
        d = by_type[t][0]
        parts.append(f"{cid},{t},{d['InternalId']};")
    return "".join(parts), []


def print_docs(docs):
    print(f"{'类型':<6}{'名称':<28}{'InternalId':>10}")
    print("-" * 48)
    for d in docs:
        print(f"{d.get('TypeName', ''):<6}{d.get('Name', ''):<28}{d.get('InternalId', ''):>10}")
    print(f"\n共 {len(docs)} 张单据")


def read_log_rows(pg):
    return pg.evaluate("""() => [...document.querySelectorAll('#operationLogList tr')]
        .map(r => [...r.cells].map(c => c.innerText.trim()))
        .filter(r => r[0])""")


def fetch_log_messages(ctx, cid, pages=3):
    """读取操作日志（最近 7 天），返回 [{time, message}]。"""
    pg = open_page(ctx, LOG_URL, "typeof load === 'function' && typeof changePage === 'function'")
    try:
        pg.evaluate("() => load()")
        pg.wait_for_function(
            "() => typeof paginationInfo === 'object' && paginationInfo !== null",
            timeout=15000)
        pg.wait_for_timeout(800)
        pg.evaluate("""(cid) => {
            document.getElementById('txt_commissionId').value = cid;
            changePage();
        }""", cid)
        pg.wait_for_timeout(1500)
        pg.wait_for_function(
            "() => document.querySelectorAll('#operationLogList tr').length > 0",
            timeout=10000)

        messages = []
        for _ in range(max(1, pages)):
            rows = read_log_rows(pg)
            for r in rows:
                messages.append({
                    "time": r[1] if len(r) > 1 else "",
                    "message": r[5] if len(r) > 5 else "",
                })
            cur = pg.evaluate("() => document.getElementById('currentPageNo').innerText")
            total = pg.evaluate("() => document.getElementById('pageNo').innerText")
            if cur == total or not rows:
                break
            first_id = rows[0][0]
            pg.evaluate("() => nextPage()")
            pg.wait_for_timeout(1500)
            new_rows = read_log_rows(pg)
            if not new_rows or new_rows[0][0] == first_id:
                break
        return messages
    finally:
        pg.close()


def run_operation(pg, cid, inst, cmd, doc_list):
    payload = {"inst": str(inst), "cmd": str(cmd), "cid": str(cid), "docs": doc_list}
    sent = pg.evaluate("""(a) => {
        _institutionOperationInfo.InstitutionId = a.inst;
        _institutionOperationInfo.CommandId = a.cmd;
        _institutionOperationInfo.CommissionId = a.cid;
        _institutionOperationInfo.DocumentList = a.docs;
        return Object.toJSON(_institutionOperationInfo);
    }""", payload)
    print("发送:", sent)
    result = pg.evaluate("""(a) => new Promise(resolve => {
        _institutionOperationInfo.InstitutionId = a.inst;
        _institutionOperationInfo.CommandId = a.cmd;
        _institutionOperationInfo.CommissionId = a.cid;
        _institutionOperationInfo.DocumentList = a.docs;
        AjaxHelper.send("Institution.ProcessOperation",
            { jsonText: Object.toJSON(_institutionOperationInfo) }, resolve);
    })""", payload)
    print("返回:", json.dumps(result, ensure_ascii=False))
    if result.get("Code") == 0 and isinstance(result.get("Value"), dict):
        node = result["Value"].get("Data1")
        text = pg.evaluate(JS_GET_NODE, node)
        print(f"节点: {node}  {text or ''}")
        return node
    return None


# ---------------------------------------------------------------- commands --
def cmd_check(args):
    ctx = connect()
    pg = ctx.new_page()
    try:
        pg.goto(HOME_URL, wait_until="domcontentloaded", timeout=30000)
        pg.wait_for_timeout(1500)
        if "Login.aspx" in pg.url:
            print("未登录：请在 Edge 中手动登录后再运行。")
            return
        print("已登录。")
        for f in pg.frames:
            print("  frame:", f.url)
    finally:
        pg.close()


def cmd_docs(args):
    cid, _ = load_case(args)
    ctx = connect()
    pg = open_page(ctx, DOC_CENTER_URL.format(cid=cid))
    try:
        docs = fetch_docs(pg, cid)
        print(f"委托 {cid} 的单据：\n")
        print_docs(docs)
    finally:
        pg.close()


def cmd_scenes(args):
    cid, role = load_case(args)
    ctx = connect()
    pg = open_page(ctx, SCENARIO_URL.format(cid=cid, inst=args.inst, role=role),
                   "typeof _scenariosHash !== 'undefined' && _scenariosHash.keys().length > 0")
    try:
        if args.all:
            data = pg.evaluate("""() => {
                const out = {};
                _scenariosHash.each(function(pair) {
                    const v = pair.value;
                    out[String(pair.key)] = (v.RoleScenarioContents || []).map(r => ({
                        type: String(r.CommandType), text: r.Content, data: r.Data
                    }));
                });
                return out;
            }""")
            for key in sorted(data, key=lambda k: int(k)):
                actions = [o for o in data[key] if o["type"] in ("1", "2", "3")]
                if actions:
                    print(f"[场景 {key}]")
                    for o in actions:
                        print(f"   commandId={o['data'][0]:<4} type={o['type']}  {o['text']}")
        else:
            scene = str(args.scene)
            opts = pg.evaluate("""(k) => {
                const v = _scenariosHash.get(k);
                return v ? (v.RoleScenarioContents || []).map(r => ({
                    type: String(r.CommandType), text: r.Content, data: r.Data
                })) : null;
            }""", scene)
            if opts is None:
                print(f"场景 {scene} 不存在。")
            else:
                for o in opts:
                    print(f"commandId={o['data'][0]:<4} type={o['type']}  {o['text']}")
    finally:
        pg.close()


def _do_operation(ctx, cid, role, inst, cmd, doc_types, raw_docs):
    pg = open_page(ctx, SCENARIO_URL.format(cid=cid, inst=inst, role=role),
                   "typeof _institutionOperationInfo !== 'undefined' && "
                   "_institutionOperationInfo !== null && "
                   "typeof _scenariosHash !== 'undefined'")
    try:
        doc_list = raw_docs
        if doc_list is None and doc_types:
            docs = fetch_docs(pg, cid)
            doc_list, missing = build_doc_list(docs, doc_types, cid)
            if missing:
                print("缺少单据类型：" + ", ".join(missing))
                return None
            print("单据:", doc_list)
        return run_operation(pg, cid, inst, cmd, doc_list)
    finally:
        pg.close()


def cmd_do(args):
    cid, role = load_case(args)
    doc_types = [t.strip() for t in args.doc_types.split(",")] if args.doc_types else None
    ctx = connect()
    _do_operation(ctx, cid, role, args.inst, args.command, doc_types, args.docs)


def cmd_step(args):
    if args.name not in STEPS:
        print("未知步骤。可用步骤：")
        for k in STEPS:
            print(f"  {k:<18}{STEP_TITLES[k]}")
        return
    cid, role = load_case(args)
    inst, cmd, doc_types = STEPS[args.name]
    if args.extra:
        doc_types = list(doc_types) + [t.strip() for t in args.extra.split(",") if t.strip()]
    print(f"步骤: {args.name}  {STEP_TITLES[args.name]}  "
          f"(institutionId={inst}, commandId={cmd})")
    ctx = connect()
    if not args.force:
        pattern = STEP_DONE_PATTERNS.get(args.name)
        hit = next((m for m in fetch_log_messages(ctx, cid)
                    if pattern and pattern in m["message"]), None)
        if hit:
            print(f"该步骤已完成（{hit['time']} {hit['message']}），已跳过。")
            print("如确需重复执行，请加 --force。")
            return
    pg = open_page(ctx, SCENARIO_URL.format(cid=cid, inst=inst, role=role),
                   "typeof _institutionOperationInfo !== 'undefined' && "
                   "_institutionOperationInfo !== null && "
                   "typeof _scenariosHash !== 'undefined'")
    try:
        doc_list = None
        if doc_types:
            docs = fetch_docs(pg, cid)
            doc_list, missing = build_doc_list(docs, doc_types, cid)
            if missing:
                print("缺少单据类型：" + ", ".join(missing))
                hint = MISSING_HINTS.get(args.name)
                if hint:
                    print("处理建议：" + hint)
                return
            print("单据:", doc_list)
        if args.dry:
            print("dry-run，未提交。")
            return
        run_operation(pg, cid, inst, cmd, doc_list)
    finally:
        pg.close()


def cmd_status(args):
    cid, _ = load_case(args)
    ctx = connect()
    msgs = fetch_log_messages(ctx, cid, pages=3)
    text = "\n".join(m["message"] for m in msgs)
    print(f"委托 {cid} 流程状态：\n")
    for i, name in enumerate(STEPS, 1):
        done = STEP_DONE_PATTERNS[name] in text
        mark = "✓" if done else " "
        print(f"[{mark}] {i:>2}. {name:<18}{STEP_TITLES[name]}")
    failures = [m for m in msgs if "重复" in m["message"]]
    if failures:
        print("\n注意：日志中有重复操作记录：")
        for m in failures:
            print(f"  {m['time']}  {m['message']}")


def cmd_log(args):
    cid, _ = load_case(args)
    ctx = connect()
    msgs = fetch_log_messages(ctx, cid, args.pages)
    print(f"委托 {cid} 的操作日志（最近 {args.pages} 页）：")
    for m in msgs:
        print(f"{m['time']}  {m['message']}")


# ------------------------------------------------------------------- main --
def main():
    ap = argparse.ArgumentParser(description="SimForwarder 自动化助手")
    ap.add_argument("--commission", help="委托编号，默认读取 case.json")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("check", help="检查 CDP 连接与登录状态")

    sub.add_parser("docs", help="列出当前委托的全部单据")

    p = sub.add_parser("scenes", help="查看某机构的可选操作及 commandId")
    p.add_argument("inst", type=int, help="机构 ID：1船公司 3检验检疫 5发货人 7堆场 9海关")
    p.add_argument("--scene", default="0", help="场景号，默认 0")
    p.add_argument("--all", action="store_true", help="列出所有可执行操作场景")

    p = sub.add_parser("do", help="直接调用一次业务操作")
    p.add_argument("inst", type=int)
    p.add_argument("command")
    p.add_argument("--doc-types", help="按单据类型自动组装，如 M2G 或 M78,M2A,M01")
    p.add_argument("--docs", help="直接指定 docList 原文")

    p = sub.add_parser("step", help="按标准流程执行一步")
    p.add_argument("name", help="步骤名，见 README/SOP")
    p.add_argument("--extra", help="额外单据类型，逗号分隔")
    p.add_argument("--dry", action="store_true", help="只打印将要提交的内容")
    p.add_argument("--force", action="store_true", help="跳过“该步骤已完成”检查")

    p = sub.add_parser("log", help="查看操作日志")
    p.add_argument("--pages", type=int, default=1)

    sub.add_parser("status", help="按标准流程显示各步骤完成情况")

    args = ap.parse_args()
    {"check": cmd_check, "docs": cmd_docs, "scenes": cmd_scenes,
     "do": cmd_do, "step": cmd_step, "log": cmd_log,
     "status": cmd_status}[args.cmd](args)


if __name__ == "__main__":
    main()
