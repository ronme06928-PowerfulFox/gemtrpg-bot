# plugins/buffs/speed_mod.py
"""
Speed modifier helpers for Bu-11 (haste) and Bu-12 (slow).

Lifecycle policy:
- Active bucket: delay=0, lasting=1
- Pending bucket: delay>=1, lasting=1
- Round-end decay handles consumption; no immediate clear on round start.
"""

from .base import BaseBuff
from manager.logs import setup_logger

logger = setup_logger(__name__)


class SpeedModBuff(BaseBuff):
    """Utility methods for haste/slow buckets."""

    BUFF_IDS = ["Bu-11", "Bu-12"]

    def apply(self, char, context):
        """
        Kept for compatibility. Main apply path is manager.utils.apply_buff.
        """
        count = int(context.get("count", 1) or 1)
        source = context.get("source", "unknown")
        if not isinstance(char, dict):
            return {"success": False, "logs": [], "changes": []}
        if "special_buffs" not in char or not isinstance(char.get("special_buffs"), list):
            char["special_buffs"] = []

        bucket = {
            "name": self.name,
            "source": source,
            "buff_id": self.buff_id,
            "delay": max(0, int(context.get("delay", 1) or 1)),
            "lasting": max(1, int(context.get("lasting", 1) or 1)),
            "is_permanent": False,
            "count": max(1, count),
            "description": self.description,
            "flavor": self.flavor,
        }
        char["special_buffs"].append(bucket)
        logger.debug("Applied %s to %s count=%s", self.name, char.get("name"), bucket["count"])
        return {"success": True, "logs": [], "changes": []}

    @staticmethod
    def _normalize_legacy_speed_buckets(char):
        """
        Convert legacy permanent speed buffs into finite active buckets.
        """
        if not isinstance(char, dict):
            return False
        buffs = char.get("special_buffs")
        if not isinstance(buffs, list):
            return False

        changed = False
        for buff in buffs:
            if not isinstance(buff, dict):
                continue
            if buff.get("buff_id") not in ["Bu-11", "Bu-12"]:
                continue

            try:
                delay = int(buff.get("delay", 0) or 0)
            except Exception:
                delay = 0
            if delay < 0:
                delay = 0
            if buff.get("delay") != delay:
                buff["delay"] = delay
                changed = True

            try:
                lasting = int(buff.get("lasting", -1) or -1)
            except Exception:
                lasting = -1
            if lasting <= 0 or bool(buff.get("is_permanent", False)):
                buff["lasting"] = 1
                buff["is_permanent"] = False
                changed = True

        return changed

    @staticmethod
    def get_speed_modifier(char):
        """
        Sum active speed modifier buckets only (delay == 0).
        """
        if not isinstance(char, dict):
            return 0
        SpeedModBuff._normalize_legacy_speed_buckets(char)

        total = 0
        for buff in char.get("special_buffs", []):
            if not isinstance(buff, dict):
                continue
            buff_id = buff.get("buff_id")
            if buff_id not in ["Bu-11", "Bu-12"]:
                continue

            try:
                delay = int(buff.get("delay", 0) or 0)
            except Exception:
                delay = 0
            if delay > 0:
                continue

            try:
                lasting = int(buff.get("lasting", 0) or 0)
            except Exception:
                lasting = 0
            if lasting == 0 and not bool(buff.get("is_permanent", False)):
                continue

            try:
                count = int(buff.get("count", 0) or 0)
            except Exception:
                count = 0
            if count <= 0:
                continue

            if buff_id == "Bu-11":
                total += count
            elif buff_id == "Bu-12":
                total -= count
        return total

    @staticmethod
    def clear_speed_modifiers(_char):
        """
        Deprecated: lifecycle is now controlled by round-end delay/lasing updates.
        """
        return False

