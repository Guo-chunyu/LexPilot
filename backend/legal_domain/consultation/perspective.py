"""Auditable consulting-side preferences, distinct from proven party identity."""
from dataclasses import replace
import re

from .profiles import PROFILES


ROLE_PATTERNS = {
    'debtor': ('借款人／被请求还款一方', r'(?:我是|本人是|我作为)(?:借款人|债务人)|我(?:向|找)[^，。；]{1,12}借了|我欠[^，。；]{0,12}钱'),
    'creditor': ('出借人／请求还款一方', r'(?:我是|本人是|我作为)(?:出借人|债权人)|我借给|欠我|向我借|借了我'),
    'landlord': ('出租人', r'(?:我是|本人是|我作为)(?:房东|出租人)'),
    'tenant': ('承租人', r'(?:我是|本人是|我作为)(?:租客|承租人)|房东[^，。；]{0,16}(?:不退|不还|不给|扣着|扣了|扣我的?)[^，。；]{0,10}押金'),
    'employer': ('用人单位一方', r'(?:我是|本人是|我代表|我作为)(?:用人单位|公司老板|公司负责人|单位负责人|公司人事|企业负责人)'),
    'employee': ('劳动者', r'(?:我是|本人是|我作为)(?:员工|劳动者|职工)|公司[^，。；]{0,8}(?:拖欠我|辞退我)'),
}
DOMAIN_ROLES = {'debt': ('debtor', 'creditor'), 'housing': ('landlord', 'tenant'), 'labor_dispute': ('employer', 'employee')}
ROLE_CORRECTIONS = {
    'debtor': r'(?:我|本人)(?:不是|并非)[^，,；;]{1,16}[，,；;]\s*(?:而)?(?:我)?是(?:借款人|债务人)',
    'creditor': r'(?:我|本人)(?:不是|并非)[^，,；;]{1,16}[，,；;]\s*(?:而)?(?:我)?是(?:出借人|债权人)',
    'landlord': r'(?:我|本人)(?:不是|并非)[^，,；;]{1,16}[，,；;]\s*(?:而)?(?:我)?是(?:房东|出租人)',
    'tenant': r'(?:我|本人)(?:不是|并非)[^，,；;]{1,16}[，,；;]\s*(?:而)?(?:我)?是(?:租客|承租人)',
    'employer': r'(?:我|本人)(?:不是|并非)[^，,；;]{1,16}[，,；;]\s*(?:而)?(?:我)?是(?:用人单位|公司负责人|企业负责人)',
    'employee': r'(?:我|本人)(?:不是|并非)[^，,；;]{1,16}[，,；;]\s*(?:而)?(?:我)?是(?:员工|劳动者|职工)',
}


def client_perspective(state, message='') -> dict:
    # Later explicit identity corrections take precedence. Never infer the role
    # merely because the other party's label occurs somewhere in a complaint.
    for text in (message, str(state.facts.get('parties', '')), state.user_narrative):
        corrected = [(rid, re.search(ROLE_CORRECTIONS[rid], text)) for rid in DOMAIN_ROLES.get(state.case_type, ())]
        corrected = [(rid, match) for rid, match in corrected if match]
        if len(corrected) == 1:
            rid, match = corrected[0]
            return {'id': rid, 'label': ROLE_PATTERNS[rid][0], 'basis': '对话陈述：' + match.group(0), 'verified': False}
        matches = [(rid, re.search(ROLE_PATTERNS[rid][1], text)) for rid in DOMAIN_ROLES.get(state.case_type, ())]
        matches = [(rid, match) for rid, match in matches if match]
        if len(matches) == 1:
            rid, match = matches[0]
            return {'id': rid, 'label': ROLE_PATTERNS[rid][0], 'basis': '对话陈述：' + match.group(0), 'verified': False}
        if len(matches) > 1:
            break
    return {'id': 'unconfirmed', 'label': '咨询者身份待确认', 'basis': '先确认本人和对方身份，再决定请求或抗辩方向。', 'verified': False}


LATER_TURN_UPDATE = re.compile(
    r'(?:回复|表示|称|主张|否认|不承认|发来|撤回|撤销)'
    r'|收到.{0,8}回复'
    r'|更正|说错了|其实是|实际是|准确说是'
    r'|只说当前一步|不用重复完整?(?:方案|全部)'
    r'|又找到了|补充找到了|后来找到了'
)


def uses_general_consultation(state, message='') -> bool:
    if state.case_type != 'labor_dispute':
        return True
    if client_perspective(state, message)['id'] == 'employer':
        return True
    # A later labour turn that reports a counterparty position, a correction or a
    # scoped next-step request is an update to an existing case, not an answer to
    # the specialist interview. It needs the shared later-turn intake and the
    # focused reply, otherwise the interview asks the same opening question again
    # and the new position never reaches `details` or the exported report.
    # The specialist path never advances `consultation.turns`, so prior
    # conversation is detected from the stored narrative instead.
    already_in_progress = bool(state.user_narrative or state.action_history)
    return already_in_progress and bool(LATER_TURN_UPDATE.search(message))


def case_profile(state):
    profile = PROFILES.get(state.case_type, PROFILES['general'])
    role = client_perspective(state)['id']
    if role == 'unconfirmed' and state.case_type in DOMAIN_ROLES:
        return replace(profile,
            focus='先明确本人和对方的身份，以及谁请求谁履行什么义务；把本金或价款、已履行金额、约定与争议分开，再确定本人请求或抗辩的方向。',
            question='你在这件事中具体是什么身份？是要求对方履行，还是对方要求你支付或承担责任？',
            route='确认双方身份和具体争议后选择相应申请或答辩材料；已收到机关文书的优先通过原案号核对办理节点，不能仅凭领域名称确定管辖。',
            defense='对方可能对义务、已经履行的部分及金额计算持不同意见，需结合双方身份逐项判断。',
            response='将本人提出的请求与对对方请求的抗辩分开，各自匹配完整原始证据和待核实条件。',
            communication='我们先逐项核对双方约定、已履行部分和争议金额。请说明每一项请求的事实、约定及材料依据，我会对应说明认可和存在异议的部分。')
    if role == 'debtor':
        return replace(profile,
            focus='先核对实际收到的本金、已还款、利息及费用依据，扣除已履行部分，对超出合法依据的请求提出具体异议；在真实偿付能力内争取可履行安排。',
            question='你实际收到多少、已还多少？对方现在要求的本金、利息和其他费用分别是多少，是否收到法院文书？',
            route='已经被起诉时按受诉法院通知提交答辩和证据，逐笔回应本金、已还款、利息与费用；未进入诉讼时先书面对账并提出真实可行的还款安排，不默认应当另行起诉。',
            defense='对方可能要求按其账单偿还全部本金、利息、违约金和费用，或申请保全。',
            response='逐笔提交实际交付与已还款记录，说明争议费用的约定和法律依据缺口；不否认已有证据的真实债务，不以隐匿财产规避执行。',
            communication='请提供实际交付本金、各笔已还款的抵扣方式及利息费用明细。我会逐项核对，对有争议部分说明理由，并根据真实收入和必要生活支出提出可以履行的安排。',
            costs='比较经核对后实际需支付的债务、可合法减免的争议费用、诉讼及代理成本；不得将暂时无力偿还等同于债务消灭。')
    if role == 'landlord':
        return replace(profile,
            focus='先核算欠租、欠费、押金及损坏项目，证明各项依据并履行出租人义务，以能实际履行的支付或交还方案减少继续损失。',
            question='欠租对应哪几个月，已收租金和押金多少？租客是否仍占用房屋，合同及交接记录如何约定？',
            defense='租客可能主张租金已经支付、房屋存在影响使用的问题、押金应抵扣或损耗属于正常使用。',
            response='用逐月账单、收款记录、房屋状态及维修履行记录回应，区分正常损耗与可证明损坏；不能默认押金可全部没收。',
            communication='请核对逐月租金应付、实付、欠付及押金账目，并提出支付或房屋交还安排；有房屋使用问题请列明，争议损坏项目另附证据核对。')
    if role == 'employer':
        return replace(profile,
            focus='从用人单位立场逐项核实员工请求，及时支付无争议的到期款项，保存真实工资与用工记录，对无依据或重复请求提交具体抗辩，减少继续扩大损失。',
            question='员工提出哪些仲裁请求？公司是否收到受理或开庭通知，工资、考勤及解除原始记录由谁保管？',
            route='已收到劳动仲裁通知时向通知上的仲裁委员会核对案号、答辩和举证节点，以被申请人身份提交答辩、公司主体和授权材料以及逐项证据；尚未受理时先核对是否确有申请，避免重复起案。',
            defense='员工可能主张欠薪、未签合同、加班费或解除赔偿；公司掌握管理资料时，不能仅以员工没有材料否认请求。',
            response='核对劳动关系、工资实际支付、考勤及解除的事实与程序，依法提供由公司掌握的记录，不补造考勤、倒签合同或删除沟通。',
            communication='我们将按你的分项请求核对合同、工资支付、考勤和解除记录。无争议的到期款项及时结算；争议项目逐项说明依据，并书面确认可履行的解决安排。',
            costs='将无争议的法定义务、争议请求、代理及内部处理成本分列；不能把拖欠工资当作降低维权成本的方法。')
    return profile


ROLE_OPERATIONS = {
    'unconfirmed': [
        '写清本人和对方分别是什么身份，谁请求谁履行什么义务；本金或价款、已履行和争议金额分别列出，不先假定本人一定是请求付款的一方。',
        '身份和争点明确后，书面核对双方义务、已履行情况与争议金额；若本人是被请求方，应先核实请求依据及已有履行证据。',
        '根据真实身份区分申请、起诉或答辩。已有案号时向原受理机关确认文书载明的节点；未进入程序时再核对有权机构及对应材料。',
        '将每一项协议义务记下由谁在何时履行，核对实际收付或交付；未解决事项单列，避免误签全部结清。'],
    'debtor': [
        '把实际到账本金、已还本金和利息逐笔对应，核对对方账单是否漏计还款或重复收费；保存原始流水，不只截取有利片段。',
        '向对方书面索取本金、还款抵扣、利息和费用明细，逐项标出争议；按真实收入和必要支出提出可执行的分期，不承诺无法兑现的日期。',
        '收到传票时通过人民法院在线服务或通知上的法院核对案号与提交节点，准备答辩状、已还款证据和争议费用明细；原告举证与你的反驳分别对应，不忽视通知。',
        '签署和解前核对剩余本金、利息处理、每期日期及违约安排，付款后取得凭证；不得转移或隐匿财产规避依法执行。'],
    'landlord': [
        '按月份列欠租、已收租金、押金和欠费，损坏另列；核对房屋仍被占用与交接现状，以及本人是否履行维修等义务。',
        '向租客已确认的联系方式送达真实的欠租明细及处理请求，保留送达记录；解除条件与催告要求先核对，禁止换锁、断水电或扣物逼退。',
        '按房屋所在地及争议类型核对管辖，准备欠租请求、合同、收款流水和催告记录；要求解除、返还房屋或赔损失时逐项说明条件，避免重复计算。',
        '交接时记录钥匙、物品、水电读数与照片，核算押金和实际有依据的扣款；区分正常损耗与租客损坏，剩余款项按核实结果结清。'],
    'employer': [
        '列出员工每项请求、公司认同与争议金额，先核对无争议到期工资；保存劳动合同、真实考勤、工资流水及解除原文。',
        '取得公司保存的工资及人事档案，逐项注明形成时间和经办人；如愿和解，将支付项目、日期及争议范围写清，不要求员工先签虚假结清证明。',
        '按仲裁通知向原仲裁委员会提交被申请人答辩、营业执照、负责人身份证明、代理授权和证据目录，记录送达日期与举证安排；不要使用劳动者申请书代替答辩。',
        '裁决送达当天核对裁决类型和单位一方适用的救济程序与期限，不能照搬劳动者的起诉路径；已确定履行事项按期处理，保留支付凭证。'],
}
