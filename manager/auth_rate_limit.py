"""Phase 2: 認証・短いコードの試行レート制限（in-memory）。

worker=1 / eventlet 前提のためプロセス内メモリで十分。再起動でリセットされる
（公開運用上は許容。永続が必要になれば差し替える）。clock を注入できるので
テストは実時間に依存しない。

password と各コードで別インスタンス（別上限）を用意する（Q26-006）。
"""
import time
from collections import defaultdict


class RateLimiter:
    def __init__(self, max_attempts, window_seconds, clock=time.time):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._clock = clock
        self._failures = defaultdict(list)  # key -> [失敗時刻]

    def _prune(self, key, now):
        cutoff = now - self.window_seconds
        self._failures[key] = [t for t in self._failures[key] if t >= cutoff]
        if not self._failures[key]:
            self._failures.pop(key, None)

    def is_allowed(self, key):
        """これ以上試行してよいか（上限未満なら True）。"""
        now = self._clock()
        self._prune(key, now)
        return len(self._failures.get(key, [])) < self.max_attempts

    def record_failure(self, key):
        now = self._clock()
        self._prune(key, now)
        self._failures[key].append(now)

    def reset(self, key):
        """成功時などに失敗履歴を消す。"""
        self._failures.pop(key, None)

    def remaining(self, key):
        now = self._clock()
        self._prune(key, now)
        return max(0, self.max_attempts - len(self._failures.get(key, [])))


# 既定インスタンス（上限値は暫定。Q26-006 で確定するまでの初期値）。
# パスワードログイン: 5分窓で10回まで。
password_login_limiter = RateLimiter(max_attempts=10, window_seconds=300)
# ワンタイムコード入力: 15分窓で5回まで（Q26-007 の方向性に合わせた初期値）。
one_time_code_limiter = RateLimiter(max_attempts=5, window_seconds=900)
