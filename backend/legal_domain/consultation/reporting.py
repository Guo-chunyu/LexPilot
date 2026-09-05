"""Actionable, explicitly provisional plans and shared readable exports."""

from datetime import datetime, timezone

from .intake import LABELS
from .models import ActionStep
from .profiles import PROFILES, domain_label
from .research import SERVICE_LINKS
from .authorities import relevant_rules


def action_plan(state) -> list[dict]:
    dossier = state.consultation
    profile = PROFILES.get(state.case_type, PROFILES['general'])
    location = str(state.facts.get('location', '案件所在地（待确认）'))
    goal = str(state.facts.get('goal', '先明确希望解决的问题'))
    material_names = [t.name for t in dossier.evidence_tasks] or ['关键合同或决定', '完整沟通记录', '时间线与证据目录']
    outside = dossier.jurisdiction_status == 'OUTSIDE_MAINLAND'
    channel = '适用地区的执业律师、法律援助机构或官方受理窗口（需先确认）' if outside else profile.channel
    first_steps = [ActionStep(
        title='先保护人身安全和程序权利' if dossier.urgent_actions else '列出事实与诉求，先核对时间节点',
        when='现在；如文书期限更早，以核实后的法定期限为先',
        channel=f'{location}的相关正式受理窗口；事实整理可先自行完成',
        materials=['本人收到的通知或决定及送达凭证', '关键事件时间线', '当前诉求与已采取行动'],
        instructions=dossier.urgent_actions or [f'把“{goal}”拆成具体请求，金额项目分别列出。', '每件事记下何时、谁、做了什么和证据编号；本人亲历、对方说法和推测分开。', '把约定履行日、收文日及文书写明的截止日单列，先向正式受理窗口核实时限和提交方式。'],
        completion='形成一页事实时间线、一份请求清单和待核对的期限表。',
        fallback='日期记不清时先找通知、订单、银行流水或送达记录；不要自行补造日期，也不要因等材料而错过办理期限。',
    ), ActionStep(
        title='按要证明的事实整理材料', when='现在开始，正式提交前再次核对原件', channel='本人设备、银行或平台导出渠道及合法保管材料的机构',
        materials=material_names,
        instructions=[f'{t.name}：{t.alternative if t.status == "暂无法提供" else t.how} 要说明：{t.proves}。' for t in dossier.evidence_tasks] or ['将材料按日期编号，记录出处、原件位置和每份材料要证明的事实。'],
        completion='每项请求均有对应证据编号；缺口明确标记，不把上传文件等同于已证明事实。',
        fallback='；'.join(t.alternative for t in dossier.evidence_tasks) or '列出材料保管人及无法取得原因，咨询依法调取、证据保存的办法。',
    )]
    if outside:
        route = '先确认国家或地区、对方住所、合同适用法和争议解决约定；携带事实摘要请当地专业人员核实实体规则、管辖及期限，再选择程序。'
    else:
        route = profile.route
    formal_first = state.case_type in ('criminal', 'administrative', 'enforcement') or bool(dossier.urgent_actions)
    first_steps.extend([
        ActionStep(
            title='通过正式渠道核对程序' if formal_first else '先提出一次清楚、可留痕的处理请求',
            when='关键材料已整理后；紧急安全或临近期限时立即办理', channel=channel if formal_first else '对方已确认的书面联络或正式平台工单渠道',
            materials=['事实摘要', '分项诉求', *material_names[:2]],
            instructions=[route if formal_first else profile.communication, '记录提交时间、材料版本、接收人或工单号；将答复与承诺逐项记下。', '协商等待时间由双方实际情况决定，不当作法定期限，也不因等待回复搁置法定救济。'],
            completion='取得回执或可核实的书面回复，并明确下一处理节点。',
            fallback='不愿接收或不回复时保留提交记录，转下一正式渠道；涉及暴力、威胁或强制措施时不要自行当面对质。',
        ),
        ActionStep(
            title='核实法源、管辖和请求后提交材料', when='确认法定期限、条件及受理机关后及时提交', channel=channel,
            materials=['适配该程序的申请书或诉状', '依法要求的身份及主体证明', '证据目录和附件', '送达信息及联系方式'],
            instructions=[route, '按受理机关最新官方清单填写事实与理由，一项请求对应一组事实和证据；不能证明的部分注明。', '保存提交凭证；收到补正要求后逐项补齐，核对补正期限、缴费及是否已正式受理。'],
            completion='拿到可查询的收件或受理信息，并确认后续举证、缴费、开庭或办理节点。',
            fallback='被退回时先取得具体原因，区分材料不足、主体或管辖问题；依据告知补正或核实救济途径，避免反复盲目提交。',
        ),
        ActionStep(
            title='准备对方抗辩与后续落实', when='收到对方意见或机关通知后，按载明期限准备', channel=channel,
            materials=['争点与证据对照表', '对方答复', '已达成协议或处理文书', '履行记录'],
            instructions=[profile.defense, profile.response, '协议或文书形成后记录履行主体、金额或事项、节点和收款情况；和解前核对是否放弃其他请求，签字内容逐字看清。'],
            completion='每个争议有事实和证据回应；结果有具体履行安排，并持续核对执行情况。',
            fallback='协商、投诉或调解未解决时重新比较正式救济成本；文书生效后仍不履行的，核对是否可依法申请执行及其条件。',
        ),
    ])
    return [step.model_dump() for step in first_steps]


def plan_documents(state) -> list[dict]:
    profile = PROFILES.get(state.case_type, PROFILES['general'])
    lines = ['材料名称 | 来源/原件位置 | 形成时间 | 要证明的事实 | 待核对问题', *[f'{t.name} | [填写] | [填写] | {t.proves} | {t.status}' for t in state.consultation.evidence_tasks]]
    return [
        {'title': '事实与诉求整理稿', 'status': '本人核对后使用', 'content': f'适用地区：{state.facts.get("location", "[待填写]")}\n本人和对方身份：[填写，提交时按要求补充正式身份信息]\n最初描述：{state.user_narrative}\n关键事实（陈述，待核实）：\n' + '\n'.join(f'- {LABELS.get(k, k)}：{v}' for k, v in state.facts.items() if k in LABELS) + '\n具体请求：[逐项写明，不清楚的金额先列计算依据]\n附件：按证据目录编号。'},
        {'title': '证据目录草稿', 'status': '补齐来源与原件信息后使用', 'content': '\n'.join(lines)},
        {'title': '沟通或窗口询问用语', 'status': '沟通草稿，不是律师函或已提交文书', 'content': profile.communication},
    ]


def build_consultation_report(state) -> dict:
    profile = PROFILES.get(state.case_type, PROFILES['general'])
    dossier = state.consultation
    steps = action_plan(state)
    summary = state.user_narrative + '\n\n当前补充：\n' + '\n'.join(f'- {LABELS.get(k, k)}：{v}' for k, v in state.facts.items() if k in LABELS)
    deadlines = [{'name': '法定申请、起诉、复议、举证或执行期限', 'status': '待核实，尚未计算截止日', 'trigger': str(state.facts.get('event_time', '案发、履行或送达日期尚不清楚')), 'action': '携带完整文书和送达记录核对适用规则、起算点、中止中断等影响；不要把建议的工作安排当作法定期限。'}]
    sources = [source.model_dump() for source in dossier.research_sources]
    report = {
        'generation_status': 'PROVISIONAL', 'generated_at': datetime.now(timezone.utc).isoformat(),
        'case_summary': summary, 'domain': domain_label(state.case_type),
        'legal_issues': state.legal_issues, 'analysis': dossier.analysis or profile.focus,
        'facts': [{'name': LABELS.get(k, k), 'value': v, 'status': '用户陈述或材料记载，待核实'} for k, v in state.facts.items() if k in LABELS],
        'fact_conflicts': dossier.conflicts, 'timeline': [t.model_dump() for t in dossier.timeline],
        'evidence_checklist': [t.model_dump() for t in dossier.evidence_tasks],
        'opponent_arguments': [profile.defense, '应对：' + profile.response],
        'action_plan': steps,
        'tailored_action_plan': [step.model_dump() for step in dossier.tailored_steps],
        'recommended_actions': [f'{step["title"]}：{step["instructions"][0]}' for step in steps],
        'costs': [profile.costs, '将必要支出、可选专业服务和可能回收的金额分开；律师费不能默认由对方承担。'],
        'deadlines': deadlines, 'documents': plan_documents(state),
        'legal_basis': relevant_rules(state), 'research_sources': sources, 'research_status': dossier.research_status,
        'compensation_estimate': {}, 'grounded_findings': [],
        'verification': {'refusal_reason': '这是现有信息下的阶段方案。事实、具体条文、时效与当地办理要求仍需核对；已提供可先执行的步骤。'},
        'risk_analysis': [{'name': '证据与法源待核验', 'description': '上传或自述不等于事实已证明，检索线索不等于适用依据。'}],
        'confidence': 0.0,
        'disclaimer': '律策是 AI 法律咨询与行动辅助工具，不是律师事务所；具体结论需结合完整证据、有效法源和当地实践核实。',
    }
    if dossier.jurisdiction_status == 'OUTSIDE_MAINLAND':
        report['research_sources'] = []
        report['research_status'] = '需另行核验适用国家或地区的法律及执业服务渠道。'
        report['analysis'] = '案件涉及中国大陆以外的地区或涉外因素。先确认适用法、管辖和当地程序，再细化法律判断。'
    state.final_report = report
    dossier.stage = '阶段方案，可继续补充'
    return report


def report_markdown(state) -> str:
    report = state.final_report
    lines = [f'# LexPilot {domain_label(state.case_type)}阶段方案', '', f'案件编号：{state.case_id}', '', '## 案情与初步分析', '', report.get('case_summary', state.user_narrative), '', report.get('analysis', '')]
    for title, values in [('主要问题', report.get('legal_issues', [])), ('对方可能怎么说及如何回应', report.get('opponent_arguments', [])), ('费用与投入', report.get('costs', []))]:
        if values:
            lines += ['', f'## {title}', '', *[f'- {v}' for v in values]]
    if report.get('fact_conflicts'):
        lines += ['', '## 需要核对的不同陈述', '', *[f'- {v["fact"]}：此前“{v["previous"]}”；本轮“{v["current"]}”。{v["status"]}' for v in report['fact_conflicts']]]
    if report.get('timeline'):
        lines += ['', '## 事实时间线', '', *[f'- {v["date_text"]}：{v["description"]}（{v["source_ref"]}；{v["status"]}）' for v in report['timeline']]]
    if report.get('evidence_checklist'):
        lines += ['', '## 证据清单', '']
        for item in report['evidence_checklist']:
            lines += [f'### {item["name"]} · {item["status"]}', '', f'证明目的：{item["proves"]}', '', f'怎么准备：{item["how"]}', '', f'暂时没有：{item["alternative"]}', '']
    for title, key in [('具体行动步骤', 'action_plan'), ('结合本案的补充步骤（AI 草案，待核对）', 'tailored_action_plan')]:
        if report.get(key):
            lines += ['', f'## {title}', '']
            for i, step in enumerate(report[key], 1):
                lines += [f'### {i}. {step["title"]}', '', f'时间安排：{step["when"]}', '', f'办理渠道：{step["channel"]}', '', '材料：' + '、'.join(step['materials']), '', *[f'- {s}' for s in step['instructions']], '', f'完成标志：{step["completion"]}', '', f'不顺利时：{step["fallback"]}', '']
    if not report.get('action_plan'):
        lines += ['', '## 建议行动', '', *[f'{i}. {s}' for i, s in enumerate(report.get('recommended_actions', []), 1)]]
    for item in report.get('deadlines', []):
        lines += ['', '## 期限核对', '', f'{item["name"]}：{item["status"]}', '', f'起算线索：{item["trigger"]}', '', item['action']]
    for item in report.get('documents', []):
        lines += ['', f'## {item["title"]}', '', item['status'], '', item['content']]
    if report.get('research_sources'):
        lines += ['', '## 法源检索线索（尚非核验结论）', '', report.get('research_status', '')]
        lines += [f'- [{s["title"]}]({s["url"]}) · {s["status"]}' for s in report['research_sources']]
    if report.get('legal_basis'):
        lines += ['', '## 有官方来源的法律规则（本案适用需核对）', '', *[f'- [{s.get("law_name", "")}{s.get("article", "")}]({s.get("source_url", "")})：{s.get("summary", "")} {s.get("applicability", "")}' for s in report['legal_basis']]]
    estimate = report.get('compensation_estimate', {})
    if estimate:
        lines += ['', '## 金额测算', '', str(estimate.get('amount', '待核对')), '', estimate.get('formula', ''), '', estimate.get('message', '')]
    lines += ['', '## 使用说明', '', report.get('verification', {}).get('refusal_reason', ''), '', report.get('disclaimer', '')]
    return '\n'.join(lines).strip() + '\n'
