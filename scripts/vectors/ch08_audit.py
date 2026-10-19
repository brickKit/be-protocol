"""Chapter 08 vectors for deleting local audit rows against the audit component's backed-up watermark (P8.22): the
receipt's epoch and storage sequence, the watermark's epoch, its ancestors with their fork points, and the retention."""
from common import write


def epoch_key(e):
    gen, timeline = e.split(".")
    return int(gen), int(timeline)


def classify(receipt, w):
    """delete, keep (not yet covered: wait) or resend (the receipt points at a lost value)."""
    epoch, seq, old = receipt["epoch"], receipt["seq"], receipt["retained"]
    if epoch == w["epoch"]:
        return "delete" if seq <= w["seq"] and old else "keep"
    if epoch in w["ancestors"]:
        fork = w["ancestors"][epoch]
        if seq > fork:
            return "resend"
        return "delete" if w["backed_up_in_epoch"] and old else "keep"
    if epoch_key(epoch) > epoch_key(w["epoch"]):
        return "keep"  # an epoch the backups have not reached yet
    return "resend"  # neither current nor on the current history: a lost branch


def audit_purge_vectors():
    w1 = {"epoch": "1.1", "seq": 100, "ancestors": {}, "backed_up_in_epoch": True}
    w2 = {"epoch": "2.1", "seq": 5, "ancestors": {"1.1": 80}, "backed_up_in_epoch": True}
    w2fresh = dict(w2, seq=0, backed_up_in_epoch=False)
    wtl = {"epoch": "1.2", "seq": 10, "ancestors": {"1.1": 100}, "backed_up_in_epoch": True}
    scenarios = [
        ("covered", "同一纪元、不高于水位、已过保留期：删除", w1, ("1.1", 100, True)),
        ("covered-young", "同一纪元、已覆盖、未满 7 天：保留", w1, ("1.1", 40, False)),
        ("past-watermark", "同一纪元、高于水位（还没进备份）：保留，等待", w1, ("1.1", 101, True)),
        ("ancestor-within-fork", "祖先纪元、不高于分叉点、新纪元已完成备份：删除", w2, ("1.1", 80, True)),
        ("ancestor-past-fork", "祖先纪元、高于分叉点（指向已丢失的值）：重新转运", w2, ("1.1", 81, True)),
        ("ancestor-past-fork-young", "高于分叉点的不论保留期都重新转运", w2, ("1.1", 95, False)),
        ("ancestor-no-backup-yet", "祖先纪元、不高于分叉点，但新纪元还没有完成备份：保留", w2fresh, ("1.1", 10, True)),
        ("current-after-restore", "恢复后的新纪元里的回执：按新纪元的水位", w2, ("2.1", 5, True)),
        ("current-after-restore-past", "新纪元里高于水位：保留", w2, ("2.1", 6, True)),
        ("later-epoch", "回执的纪元晚于水位的纪元（备份还没追上）：保留，等待", w1, ("1.2", 3, True)),
        ("later-generation", "回执的恢复代次更大：保留，等待", w1, ("2.1", 1, True)),
        ("lost-branch", "纪元不在当前历史中（从更早的备份恢复，整条分支丢弃）：重新转运", w2, ("1.2", 3, True)),
        ("lost-branch-older", "更早的、不在历史中的纪元：重新转运", w2, ("0.9", 3, True)),
        ("timeline-ancestor", "高可用切换（时间线变大）后的旧时间线、不高于分叉点：删除", wtl, ("1.1", 100, True)),
        ("timeline-current", "切换后新时间线里的回执：按新时间线的水位", wtl, ("1.2", 10, True)),
    ]
    cases = []
    for cid, note, w, (epoch, seq, retained) in scenarios:
        r = {"epoch": epoch, "seq": seq, "retained": retained}
        cases.append({"id": cid, "note": note, "watermark": w, "receipt": r, "expect": classify(r, w)})
    write("audit-purge", ["P8.22"],
          "本地审计行（已有回执）能不能删除。watermark 是审计组件的已备份水位：epoch（当前纪元，“部署恢复代次.时间线”）、"
          "seq（已进备份的最高存储序号）、ancestors（当前历史上的祖先纪元与各自的分叉点）、backed_up_in_epoch（当前纪元里是否"
          "已完成过一次备份）。receipt 是回执的纪元与存储序号，retained 表示已超过最短保留期（7 天）。expect：delete（删除）、"
          "keep（保留，等水位追上或保留期满）、resend（回执指向已丢失的值：改回待转运，按记录身份重新发送）。判断：同一纪元按"
          "水位；祖先纪元高于分叉点 resend，不高于分叉点且当前纪元已完成备份才可删除；比水位的纪元更晚的 keep；其余（不在"
          "当前历史中）resend。resend 不看保留期。",
          cases, {"watermark": "已备份水位", "receipt": "一条已有回执的本地行", "expect": "delete、keep 或 resend"})
