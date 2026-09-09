"""Explainable user-interest planning. No invented win probabilities or returns."""
import re

from .perspective import case_profile, client_perspective, ROLE_OPERATIONS, DOMAIN_ROLES


# Practical preparation and conditional routes, not a substitute for venue rules.
OPERATIONS = {
    'debt': [
        '建立欠款明细：本金交付、每次还款、剩余本金、约定利息分别列行；转账备注、借条和聊天中“借款/还款”对应同一笔交易。只有转账时，还要补充款项用途，不能直接认定是借款。',
        '将书面催款发到对方常用账号或约定送达地址：“请核对借款日期、已交付本金、已还款及剩余金额；请书面回复还款安排。”保留完整会话与送达凭证，不替对方编写承认内容。',
        '进入人民法院在线服务，先根据被告住所、合同履行地及管辖约定核对受理法院，再填写民事起诉材料：诉求逐项写剩余本金、具备依据的利息和费用。同步上传转账、借条或聊天与证据目录，保存提交编号。',
        '发现对方转移财产线索或拒不履行时，整理本人合法掌握的财产线索并询问财产保全的条件、担保和错误保全责任；生效文书仍未履行，再核对执行申请。'],
    'housing': [
        '将租金、押金、欠费和已退款分开核算。保留租约、付款凭证、退租通知；逐房间拍摄原始交接照片或视频，记录钥匙交还和水电表读数。',
        '向出租人书面索取逐项扣款理由、对应合同条款、交接照片和实际维修凭证；区分正常使用损耗与本人造成的损坏，提出无争议部分先退。',
        '核对房屋所在地及租赁纠纷管辖，使用人民法院在线服务或相应法院诉讼服务中心。申请退押金时分别列押金已交、退租交接、扣款争议和金额依据，附对应编号证据。',
        '任何部分退款均保存收款记录；涉及“全部结清、放弃任何权利”的确认书先核对剩余争议，不能未收到承诺款项就按全部履行签字。'],
    'consumer': [
        '导出订单、付款、商家经营主体、广告承诺、合同及剩余服务次数；充值余额和赠送金额分开列，保存停业公告或拒绝服务的原始记录。',
        '在商家客服或交易平台开正式退款工单，写明订单、未履行内容、退款计算和所附材料；要求回复处理安排并保存工单号。',
        '打开全国12315平台，消费争议选投诉，违法线索选举报；填写实际经营主体、商品或服务、交易时间、争议事实和具体请求，上传订单及交涉记录。查看受理和反馈节点。',
        '投诉未解决且对方仍有可履行能力时，比较诉讼投入；不得把监管处罚或举报等同于个人退款。存在欺诈线索时先核对法定构成和对应证据，再决定是否追加赔偿请求。'],
    'labor_dispute': [
        '按月列应发工资、实发工资、差额；解除补偿、违法解除赔偿、加班费等分开计算并注明条件，同一解除不能当然同时领取经济补偿和违法解除赔偿。',
        '从银行导出工资流水，保留劳动合同、考勤、工作安排和解除原文；向公司书面索取工资构成、离职理由及结算明细，保存送达记录。',
        '联系劳动合同履行地或用人单位所在地的劳动人事争议仲裁委员会，先核对管辖；填写仲裁申请书中的双方身份、分项请求、事实理由，附身份与主体信息、证据目录，核对份数后网上或窗口提交。',
        '拿到收件回执后核对是否受理、补正期限和开庭举证安排；仲裁裁决到达当天保存送达凭证，区分裁决类型和本人身份，再核对后续救济期限。'],
    'family': [
        '先区分协议离婚或诉讼离婚、人身安全、子女照护和财产债务；列财产取得时间、登记人、贷款和日常照护事实，保留本人可合法取得的凭证。',
        '协商时把子女安排、抚养费、财产交付、债务承担逐项写清；受到暴力或威胁时优先报警、就医并询问人身安全保护令，避免当面对质。',
        '双方自愿且能达成协议时，向婚姻登记机关查询现行离婚登记要求、预约与两次到场节点；不能达成协议时，核对法院管辖，准备婚姻关系、子女和争议财产材料。',
        '不擅自转移共同财产，不让孩子传话或收集对方隐私；协议签署和履行时间、房屋过户、款项支付等逐项记录。'],
    'criminal': [
        '拍照保存拘留、逮捕或其他通知的完整内容和收到时间，记录办案机关、案号、关押地点与本人和涉案人的关系；有通知不清楚的内容向通知机关核实。',
        '联系办理刑事案件的执业律师，或通过12348核对法律援助条件；说明现处阶段、已知罪名或措施、健康等情况，确认委托范围与费用。',
        '由依法有权的人员向办案机关了解程序，律师依法办理会见、申请变更强制措施等；家属整理真实的身份、医疗和生活情况材料，不承诺能够取保或撤案。',
        '保存可能有利或不利的原始材料及来源，交由辩护人员依法判断；不串供、不毁灭证据、不联系证人施压，赔偿或谅解也不能保证消除刑事责任。'],
    'administrative': [
        '扫描决定书、告知书、信封或电子送达记录，逐字抄录文书所写救济机关、途径和期限，记录实际收到日期及此前陈述申辩过程。',
        '列出具体异议：事实、证据、程序、法律适用或裁量分别写；提出获取与本人有关的案卷材料请求并保留记录。',
        '先核对该事项是否复议前置以及复议机关或行政诉讼管辖。复议按被申请机关和行为类型确认受理机关，使用该机关正式平台或收件窗口提交申请及决定与送达材料。',
        '不因投诉或信访等待而搁置复议、起诉期限；是否停止执行需要单独核对规则及申请条件，不能自行认为提出异议就能不执行。'],
    'enforcement': [
        '整理生效判决、裁定、调解书等执行依据，生效与送达信息，分项列文书确定义务、履行期、已履行和未履行部分。',
        '已立执行案的先提供案号及历次通知，通过执行法院正式渠道提交新线索；未立案的核对执行管辖和申请期限，避免重复新建同一申请。',
        '在人民法院在线服务的执行相关入口或执行事务窗口提交申请执行书、身份材料、生效文书与未履行明细；财产线索说明来源和关联，不购买个人信息。',
        '记录执行案号、承办联系渠道和每次处理答复；遇到终结本次执行、执行异议等文书，核对其实际含义和救济程序，新发现财产再依法补充。'],
    'medical': [
        '治疗安全优先。向医院病案管理部门申请复制本人病历并核对盖章与页数，保存费用清单、影像、处方、告知同意书与损害发生时间线。',
        '将认为诊疗不妥的具体环节和损害变化写给医院医疗纠纷接待部门，询问病历封存、回复及调解安排，保存接收凭证。',
        '核对当地医疗纠纷人民调解委员会或法院办理路径；鉴定前明确争议问题、所需材料、委托主体与费用，避免自行重复做不适配程序的鉴定。',
        '误诊或治疗结果不佳不能直接等同于医疗过错；将过错、因果关系和损害项目分别对应证据，继续保存后续治疗费用。'],
    'traffic': [
        '确保救治和现场安全，依法报警、联系保险；保留事故认定文书、送达日期、现场资料、就诊与费用记录。',
        '列车辆与保险主体、责任争议、损失项目和垫付款；向保险公司报案并索取理赔材料清单、报案号和书面核损依据。',
        '对事故认定存在异议时，按文书载明程序先核对复核机关与期限；赔偿争议另行比较保险理赔、调解和法院诉讼，必要鉴定先确认时机与委托要求。',
        '签署赔偿结清协议前核对后续治疗、护理、误工及其他符合条件的项目，未明确的长期损失不要轻率写已全部结清。'],
    'corporate': [
        '整理股东名册、出资凭证、章程、登记资料和争议决议；区分公司财产、个人出资、股权价格与分红，不混作可直接取走的个人资金。',
        '提出查阅请求时列明股东身份、材料范围和目的，向公司正式地址或确认的电子渠道送达，保存接收与拒绝记录。',
        '按知情权、决议效力、股权转让、出资责任或清算确定请求，核对行为发生日的公司法版本及过渡规则；准备公司登记与基础权利材料后核对法院或仲裁约定。',
        '先确定需要解决的争点，再询价审计评估或代理服务；不能未经授权获取商业秘密，也不能默认股东对全部公司债务承担责任。'],
    'inheritance': [
        '整理死亡证明、亲属关系、遗嘱或遗赠扶养协议，分别列财产、债务及保管人；先区分遗产与他人共有财产。',
        '通知已知利害关系人核对清单和现有文书，保存遗嘱原件与形成线索，不自行涂改、藏匿或只提供有利片段。',
        '无争议时向财产对应登记机构核对继承转移材料及是否需要公证；存在身份、遗嘱或份额争议时，核对继承诉讼管辖后提交身份链和财产线索。',
        '签分割协议前核对遗产债务、共有份额和交付过户条件；暂时找不到原件时列明保管人和查找过程，不编造遗嘱。'],
    'intellectual_property': [
        '保存创作源文件、首次发表、登记或授权合同；同时固定侵权页面完整网址、账号、时间、使用内容和交易线索。',
        '向平台知识产权入口提交权利证明、原作与侵权内容对比、具体链接和处理请求，保存申诉编号与反通知。',
        '按著作权、商标、专利或商业秘密区分管理机关及法院管辖；易灭失的网络内容先核对公证或其他合法保存方式，起诉前分别证明权属、行为和损失依据。',
        '对方下架后仍保存原始证据；请求赔偿时区分实际损失、侵权获利等依据，不只凭阅读量或截图推算确定收益。'],
    'tort': [
        '先停止继续受损并就医或采取必要保护；保存原始侵权内容、时间、传播范围、费用凭证和相关人员信息。',
        '通过平台或对方正式渠道提出停止侵害、删除特定内容、纠正或赔偿等对应请求，保留原文和工单。',
        '按侵权类型核对法院管辖和诉求，分别列行为、过错或特别责任条件、损害和因果关系，材料缺失时标明保管人及合法调取线索。',
        '不通过公开对方住址、辱骂或威胁扩大冲突；跟踪停止侵害和实际履行情况，新增损失另行记录。'],
    'contract': [
        '把合同、补充协议、订单、交付验收、付款与催告按时间排好，列本人和对方各自应做、已做及未做事项。',
        '向对方发出具体履行或补救请求：对应合同义务、缺陷、所需动作和回复安排；是否解除及是否还应继续本人履行须先核对条件。',
        '先查看争议解决条款是否有效以及约定机构，再选择商事仲裁或法院；分项说明继续履行、解除、退款、损失或违约金，防止重复计算互不兼容的请求。',
        '继续采取合理措施减少损失并保存支出依据；第三方替代交易、违约金和可得利益分别说明必要性及可证明范围。'],
}


def compare_routes(state) -> dict:
    profile = case_profile(state)
    role = client_perspective(state)
    urgent = bool(state.consultation.urgent_actions)
    formal_only = state.case_type in ('criminal', 'administrative', 'enforcement')
    procedure = str(state.facts.get('procedure', ''))
    constraints = str(state.facts.get('constraints', ''))
    failed = bool(re.search(r'拒绝|不回复|不理|协商.{0,8}(?:不成|失败|三次)|调解失败', procedure))
    filed = bool(re.search(r'已经起诉|已立案|收到.{0,8}(?:传票|开庭)|已经申请仲裁', procedure))
    formal_preference = bool(re.search(r'不想再.{0,10}(?:催款|协商|调解)|(?:准备|直接|转为?).{0,8}(?:起诉|仲裁|正式程序)', constraints))
    recommended = 'formal' if urgent or formal_only or filed or formal_preference else 'mediation' if failed else 'negotiation'
    route_data = [
        ('negotiation', '一次可留痕的协商', '自行处理通常无需程序费；重点是书面回复和实际到账',
         '可控、关系成本较低，适合尚未交涉且对方愿意沟通；已有拒绝时不重复消耗时间', '拒绝、超过双方约定回复安排或临近法定期限时转正式渠道'),
        ('mediation', '平台处理或适配的调解', '先询问免费公共渠道；平台处理或调解不能保证追回款项',
         '已有协商障碍且适合自愿调解时引入第三方；确认协议效力和履行保障', '对方不参加、调解不成或期限临近时转正式救济'),
        ('formal', '有管辖权机关的正式程序', profile.costs,
         '优先保护到期的程序权利，或处理已经进入正式程序的事项；费用与执行可能分开衡量', '材料被退回时按具体理由补正，收到文书当天核对下一期限'),
    ]
    routes = [{'id': rid, 'name': name, 'cost': cost, 'reason': reason, 'stop_condition': stop,
        'eligible': rid == 'formal' or not (formal_only or urgent or filed or formal_preference), 'recommended': rid == recommended} for rid, name, cost, reason, stop in route_data]
    return {'model': 'transparent_preference_rules', 'client_role': role, 'recommended_route': recommended, 'routes': routes,
        'success_probability': None,
        'objective': '优先止损与保住权利；在可执行性、费用、时间和用户偏好之间选择合法维权路径。',
        'decision_reason': '存在紧急事项，先保护程序权利。' if urgent else '用户已明确不再继续协商并要求准备正式程序。' if formal_preference else '已经进入或应当使用正式程序。' if formal_only or filed else '此前协商已受阻，转适配的第三方渠道并保留正式救济。' if failed else '先争取低投入的实际履行，同时准备证据与正式救济材料。',
        'benefit_worksheet': ['把已发生的损失与有证据支持的请求分开列，避免重复主张同一损失。',
            '比较总支出＝有依据的应付款项－可依法减免或已支付部分＋程序、取证、代理等成本；先核实义务，不能靠逃避履行制造收益。' if role['id'] in ('debtor', 'employer') else '比较到手净额＝实际收到的款项－本人承担的程序、取证、代理及必要出行成本。',
            '协商底线由本人根据急需用款、可执行财产、证据和预算决定；不把模型生成的数字当胜率或收益。',
            '分期和解写明金额、每期日期、付款账户、违约安排和可依法取得的履行保障；以实际到账核对，不提前确认全部结清。']}


def _adapt_operations_to_available_evidence(state, operations: list[str]) -> list[str]:
    unavailable = {
        task.name for task in state.consultation.evidence_tasks
        if task.status == '暂无法提供'
    }
    if state.case_type != 'debt' or '借条' not in unavailable:
        return operations
    adapted = []
    for operation in operations:
        operation = operation.replace(
            '转账备注、借条和聊天中“借款/还款”',
            '现有转账记录和聊天中“借款/还款”',
        )
        operation = operation.replace(
            '同步上传转账、借条或聊天与证据目录',
            '同步上传现有转账、聊天及证据目录',
        )
        adapted.append(operation)
    return adapted


def enhance_steps(state, steps: list[dict]) -> list[dict]:
    urgent = bool(state.consultation.urgent_actions)
    outside = state.consultation.jurisdiction_status == 'OUTSIDE_MAINLAND'
    role = client_perspective(state)['id']
    operations = ROLE_OPERATIONS.get(role, OPERATIONS.get(state.case_type, [])) if state.case_type in DOMAIN_ROLES else OPERATIONS.get(state.case_type, [])
    operations = _adapt_operations_to_available_evidence(state, operations)
    if outside:
        operations = []
    relative_schedule = ('立即', '立即', '材料整理后', '程序条件核对后', '收到对方意见或机关通知后')
    for index, step in enumerate(steps):
        step['suggested_date'] = '立即' if urgent else relative_schedule[min(index, 4)]
        step['date_note'] = '这是相对行动顺序，不是法定期限；文书期限更早时优先处理。线下办理先核对工作时间。'
        if not outside and operations:
            if index == 0:
                step['instructions'].insert(0, operations[0])
                if not urgent:
                    step['channel'] = '先在本人手机或电脑整理，无需到窗口'
            elif index == 2:
                step['instructions'].insert(0, operations[1])
            elif index == 3:
                step['instructions'].insert(0, operations[2])
            elif index == 4:
                step['instructions'].insert(0, operations[3])
    # Urgent preservation remains the first instruction and first action.
    if urgent:
        steps[0]['instructions'] = list(dict.fromkeys([*state.consultation.urgent_actions, *steps[0]['instructions']]))
    if not outside and len(steps) > 2:
        route = compare_routes(state)['recommended_route']
        profile = case_profile(state)
        if route == 'mediation':
            steps[2].update(title='协商已经受阻，转适配的调解渠道',
                channel='全国12315平台的消费投诉渠道' if state.case_type == 'consumer' else '中国法律服务网查询的当地人民调解机构；医疗争议优先核对医疗纠纷调解机构',
                instructions=['把此前交涉时间、对方拒绝内容、尚未解决的请求整理成一页，附上原始交涉记录，说明已协商失败。',
                    '通过下方官方办理入口核对适配的第三方渠道，提交请求与证据目录，询问是否需要对方同意参加、预计联系节点以及协议效力。',
                    '对方拒绝参加或调解不成时保存结果，转下一正式救济步骤；临近法定期限时直接保护程序权利，不再等待。'],
                completion='取得投诉编号、调解联系信息或不受理／不参加的明确答复，并记下下一办理节点。')
        elif route == 'formal' and state.case_type not in ('criminal', 'administrative', 'enforcement'):
            steps[2].update(title='优先处理正式程序和文书节点', channel=profile.channel,
                instructions=['查找最新通知、案号和送达凭证；已经立案的使用原案号核对举证、补正、缴费或开庭节点，不重复新建同一案件。',
                    '尚未立案但存在紧迫期限时，先核对有管辖权机构及提交方式，按已有材料准备申请并记录缺口；不要为继续协商错过期限。',
                    '保存提交凭证，明确当前只是收件还是已经受理，依通知完成下一项办理。'])
    return steps
