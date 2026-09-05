"""
Legal synonym dictionary - maps colloquial terms to formal Company Law terminology.
Applied before retrieval to bridge the semantic gap between user queries and legal text.
"""
import re

# Colloquial -> Legal term pairs
SYNONYM_MAP = [
    # Director removal
    ("罢免董事", "选举和更换非由职工代表担任的董事"),
    ("开除董事", "选举和更换非由职工代表担任的董事"),
    ("换董事", "选举和更换非由职工代表担任的董事"),
    # Shareholder exit
    ("退股", "股权转让 异议股东回购请求权 减资"),
    ("退出公司", "股权转让 回购 减资 解散清算"),
    ("股东退出", "股权转让 异议股东股权回购请求权"),
    # Company dissolution
    ("公司关门", "公司解散 清算"),
    ("公司倒闭", "解散 清算 破产"),
    ("解散公司", "公司解散 清算事由"),
    # Shareholder guarantee
    ("给股东担保", "为股东提供担保 股东会决议 回避表决"),
    ("公司担保", "提供担保 股东会决议 回避"),
    # Voting rights
    ("表决权不同", "表决权 出资比例 章程另有规定 类别股"),
    ("一票否决", "表决权 章程规定"),
    # Document access
    ("查账", "查阅会计账簿 股东知情权"),
    ("看账本", "查阅复制 财务会计报告"),
    ("看公司文件", "查阅复制 股东知情权"),
    # Capital
    ("注册资金", "注册资本"),
    ("减少注册资金", "减少注册资本 减资"),
    # General mapping
    ("公司法第", "公司法 第"),
    ("不合规", "违反 禁止 无效 章程不得"),
]

def expand_query(query: str) -> str:
    """Augment query with legal synonyms for better retrieval."""
    result = query
    for colloquial, legal in SYNONYM_MAP:
        if colloquial in query:
            # Replace colloquial term with legal term phrase
            result = result.replace(colloquial, f"{colloquial} {legal}")
    return result
