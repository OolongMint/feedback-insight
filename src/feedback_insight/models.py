from dataclasses import asdict, dataclass

TOPICS = ('性能与稳定性', '账号与登录', '付费与订单', '功能需求', '使用体验', '其他')
SENTIMENTS = ('正向', '中性', '负向')


@dataclass
class Feedback:
    source_row: int
    text: str
    date: str
    channel: str
    user_id: str
    topic: str = '其他'
    sentiment: str = '中性'
    severity: int = 1
    quarantined: bool = False

    def to_dict(self):
        return asdict(self)
