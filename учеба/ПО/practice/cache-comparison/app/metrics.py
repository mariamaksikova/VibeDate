import threading
from dataclasses import dataclass, field


@dataclass
class Metrics:
    db_reads: int = 0
    db_writes: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    write_back_pending_peak: int = 0
    write_back_flush_runs: int = 0
    write_back_rows_flushed: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "db_reads": self.db_reads,
                "db_writes": self.db_writes,
                "cache_hits": self.cache_hits,
                "cache_misses": self.cache_misses,
                "cache_requests": self.cache_hits + self.cache_misses,
                "hit_rate": (
                    self.cache_hits / (self.cache_hits + self.cache_misses)
                    if (self.cache_hits + self.cache_misses) > 0
                    else 0.0
                ),
                "write_back_pending_peak": self.write_back_pending_peak,
                "write_back_flush_runs": self.write_back_flush_runs,
                "write_back_rows_flushed": self.write_back_rows_flushed,
            }

    def reset(self) -> None:
        with self._lock:
            self.db_reads = 0
            self.db_writes = 0
            self.cache_hits = 0
            self.cache_misses = 0
            self.write_back_pending_peak = 0
            self.write_back_flush_runs = 0
            self.write_back_rows_flushed = 0

    def inc_db_read(self, n: int = 1) -> None:
        with self._lock:
            self.db_reads += n

    def inc_db_write(self, n: int = 1) -> None:
        with self._lock:
            self.db_writes += n

    def record_cache_hit(self) -> None:
        with self._lock:
            self.cache_hits += 1

    def record_cache_miss(self) -> None:
        with self._lock:
            self.cache_misses += 1

    def record_write_back_flush(self, rows: int, pending_now: int) -> None:
        with self._lock:
            self.write_back_flush_runs += 1
            self.write_back_rows_flushed += rows
            if pending_now > self.write_back_pending_peak:
                self.write_back_pending_peak = pending_now

    def update_write_back_pending_peak(self, pending: int) -> None:
        with self._lock:
            if pending > self.write_back_pending_peak:
                self.write_back_pending_peak = pending


metrics = Metrics()
