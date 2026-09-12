"""Human-facing wording pools.

The analysis layer needs fixed templates: they keep legal answers deterministic,
auditable and free of invented content. The *wording* layer must not be fixed,
otherwise every turn reads like the same filled-in form.

Everything here is presentation only. Nothing in this module may change which
fact, evidence task or legal route is selected.
"""

from __future__ import annotations

from typing import Sequence

# Keep the bounded recent-variant memory small; it only needs to cover a
# handful of adjacent turns.
RECENT_MEMORY = 12


def pick_variant(pool: Sequence[str], recent: Sequence[str], turn: int) -> str:
    """Rotate through `pool`, skipping variants used in the recent turns.

    Deterministic for a given (pool, recent, turn) triple so replays and tests
    stay stable, while still avoiding an obvious repeat.
    """
    if not pool:
        return ''
    candidates = [item for item in pool if item not in recent] or list(pool)
    return candidates[turn % len(candidates)]


# Generic acknowledgement used when no fact-specific lead applies.
GENERIC_LEAD_POOL = (
    '明白，这一点我记下了。',
    '好的，我们接着往下梳理。',
    '了解，再确认一个细节。',
    '记下了，接着看下面这一点。',
    '好，这部分清楚了。',
    '收到，还有一个点要确认。',
    '明白，下面这个信息挺关键。',
    '好的，继续。',
    '清楚了，再问一个。',
    '明白，我们往前推进一点。',
    '好，这个我记下了。',
    '了解，接下来确认一件事。',
)

# Lead-in before the next fact question, keyed by the fact being asked.
FACT_LEAD_POOLS: dict[str, tuple[str, ...]] = {
    'contract_term_months': (
        '好，签合同这一点我记下了。',
        '合同的事清楚了。',
        '记下了，你们签过合同。',
    ),
    'probation_period_months': (
        '明白，我们再看合同里的试用期约定。',
        '好，接着看试用期。',
        '试用期这块我记下了。',
    ),
    'recruitment_conditions_disclosed': (
        '好的，我再确认一下入职时的情况。',
        '入职时的情况我记下了。',
        '好，接着问入职那一段。',
    ),
    'assessment_evidence_exists': (
        '知道了。接下来要看公司说你不合格时有没有依据。',
        '明白，那就看公司有没有依据。',
        '记下了，下面看考核依据。',
    ),
    'termination_reason': (
        '前面的情况清楚了，我还想确认公司当时的说法。',
        '好，那公司当时是怎么说的？',
        '前面的记下了，再看解除理由。',
    ),
    'written_termination_notice': (
        '明白。再确认一下解除手续。',
        '好，解除手续这块再确认一下。',
        '记下了，接着看有没有书面通知。',
    ),
    'monthly_salary': (
        '前面的情况基本清楚了。为了估算可能涉及的金额，',
        '好，金额这块要确认一下，',
        '前面的都记下了，为了估算金额，',
    ),
    'employment_duration_months': (
        '好的。工作年限会影响后面的金额估算，',
        '工作年限这块我记下了，',
        '好，年限会影响估算，',
    ),
    'unsigned_months': (
        '明白。为了算清未签合同的时间，',
        '好，未签合同的时长要确认，',
        '记下了，为了算清这段时间，',
    ),
    'arrears_amount': (
        '好的。为了把欠薪金额算清楚，',
        '欠薪金额这块要确认，',
        '好，把欠多少算清楚，',
    ),
    'overtime_hours': (
        '了解。为了进一步估算加班费，',
        '加班这块要确认，',
        '好，加班时间记一下，',
    ),
}

# Re-ask wording when the same fact is still outstanding.
REPHRASE_POOLS: dict[str, tuple[str, ...]] = {
    'monthly_salary': (
        '刚才这个数字我没有识别准确，我换个问法：你平时一个月工资大约多少钱？'
        '像“一万”“10000元”或“每月一万”都可以。',
        '这个数字我再确认一次：你一个月工资大概多少？说“一万”这样的约数就行。',
        '工资这块我再问得直接一点：每月大概到手或约定多少？',
    ),
    'contract_term_months': (
        '我换个更直接的问法：劳动合同写的是几年？如果是无固定期限，也可以直接这样说。',
        '合同期限我再确认一下：签的是几年，还是无固定期限？',
        '换个说法问：这份合同约定的期限是多长？',
    ),
    'probation_period_months': (
        '我换个说法：合同上写了几个月试用期？',
        '试用期我再确认一次：合同里写的是几个月？',
        '换个问法：试用期约定了多久？',
    ),
    'employment_duration_months': (
        '我再确认一下：从入职到现在或离职，一共工作了几年几个月？',
        '工作时长我换个问法：你在这家单位前后做了多久？',
        '再说一次年限：入职到结束一共多长时间？',
    ),
}

# Opening of an evidence request.
EVIDENCE_INTRO_POOL = (
    '情况我已经大致理清了。',
    '好，基本情况清楚了。',
    '前面这些我记下了。',
    '明白，情况大致就是这样。',
    '好，到这里情况基本清楚了。',
)

EVIDENCE_REQUEST_POOL = (
    '接下来最好把关键材料固定下来，你可以先看看手头有没有：',
    '下面这些材料如果有的话，最好先归拢到一起：',
    '下一步建议先把能证明关键事实的材料固定下来：',
    '这些材料对后面的判断很重要，先看看手边有没有：',
)

# Lead-in for the single most relevant next step.
SINGLE_STEP_POOL = (
    '眼下最关键的一步是',
    '现在最该做的是',
    '接下来优先做这一步：',
    '这一步可以先走起来：',
    '当前最值得先做的是',
)

# Pointer to the structured report panel.
REPORT_POINTER_POOL = (
    '右侧“报告”已按本轮消息更新，完整步骤和导出内容以当前版本为准。',
    '完整步骤和导出文件在右侧“报告”，以当前版本为准。',
    '右侧“报告”同步更新了，完整内容以它为准。',
    '更完整的步骤在右侧“报告”，可随时下载。',
)

# Opening of a first full-plan answer.
PLAN_INTRO_POOL = (
    '按现有信息，可以先这样推进：',
    '就目前掌握的情况，建议按这个顺序走：',
    '现在可以先按下面几步推进：',
    '基于目前的事实，先照这个顺序处理：',
)

# Stage-plan reply produced by the labour specialist path.
STAGE_PLAN_INTRO_POOL = (
    '可以先按现有材料推进，尚未证实的事实与法源缺口会保留在报告中。',
    '现有材料下可以先推进起来；还没证实的事实和法源缺口会保留在报告里。',
    '按目前已有的材料，可以先动起来；未证实的部分仍标记为待核实。',
)

STAGE_PLAN_OUTRO_POOL = (
    '右侧报告已列出完整步骤、材料和沟通草稿；你可以继续补充事实或问其中某一步。',
    '完整步骤、材料和沟通草稿在右侧报告；继续补充事实，或者直接问其中某一步都可以。',
    '报告里放了完整步骤和沟通草稿，你可以继续补事实，也可以就某一步追问。',
)


class WordingComposer:
    """Picks non-repeating wording for one consultation turn.

    Backed by the dossier so the choice survives serialization: a restored
    session keeps avoiding what it already said.
    """

    def __init__(self, dossier) -> None:
        self._dossier = dossier

    def _pick(self, pool: Sequence[str]) -> str:
        variant = pick_variant(pool, self._dossier.wording_recent, self._dossier.turns)
        recent = list(self._dossier.wording_recent)
        recent.append(variant)
        self._dossier.wording_recent = recent[-RECENT_MEMORY:]
        return variant

    def generic_lead(self) -> str:
        return self._pick(GENERIC_LEAD_POOL)

    def fact_lead(self, fact_id: str) -> str:
        pool = FACT_LEAD_POOLS.get(fact_id)
        return self._pick(pool) if pool else ''

    def rephrase(self, fact_id: str, question: str) -> str:
        pool = REPHRASE_POOLS.get(fact_id)
        if pool:
            return self._pick(pool)
        return f'这条信息我还没确认下来，我换个更直接的问法：{question}如果确实不清楚，直接告诉我“不知道”就可以。'

    def evidence_intro(self, transition: str = '') -> str:
        return transition or self._pick(EVIDENCE_INTRO_POOL)

    def evidence_request(self) -> str:
        return self._pick(EVIDENCE_REQUEST_POOL)

    def single_step_lead(self) -> str:
        return self._pick(SINGLE_STEP_POOL)

    def report_pointer(self) -> str:
        return self._pick(REPORT_POINTER_POOL)

    def plan_intro(self) -> str:
        return self._pick(PLAN_INTRO_POOL)

    def stage_plan_intro(self) -> str:
        return self._pick(STAGE_PLAN_INTRO_POOL)

    def stage_plan_outro(self) -> str:
        return self._pick(STAGE_PLAN_OUTRO_POOL)
