"""
Async CSV save queue with a background worker thread.

Debounced saves are enqueued and written on a background thread to avoid
blocking the UI during rapid typing. Flush ensures pending saves complete
before navigation or app close.
"""

import csv
import logging
import queue
import threading

logger = logging.getLogger(__name__)


def _write_csv_to_disk(csv_path: str, rows: list[list]) -> bool:
    """Write rows to CSV file. Thread-safe; call from worker only."""
    if not csv_path:
        return False
    try:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerows(rows)
        logger.info("Saved CSV to %s", csv_path)
        return True
    except Exception as e:
        logger.error("Error saving CSV: %s", e)
        return False


_FLUSH_SENTINEL = None


class CsvSaveQueue:
    """
    Queue for deferred CSV saves, serviced by a background thread.

    Call enqueue_save() with a snapshot of (path, rows). The worker writes
    to disk without blocking the main thread. flush() waits for the queue
    to drain.
    """

    def __init__(self):
        self._queue: queue.Queue[tuple[str, list[list]] | None] = queue.Queue()
        self._flush_event = threading.Event()
        self._worker = threading.Thread(target=self._run_worker, daemon=True)
        self._worker.start()

    def _run_worker(self) -> None:
        while True:
            item = self._queue.get()
            if item is _FLUSH_SENTINEL:
                self._flush_event.set()
                continue
            csv_path, rows = item
            _write_csv_to_disk(csv_path, rows)

    def enqueue_save(self, csv_path: str, rows: list[list]) -> None:
        """Enqueue a save. Rows are copied; safe to call from main thread."""
        snapshot = [row[:] for row in rows]
        self._queue.put((csv_path, snapshot))

    def flush(self, csv_path: str | None, rows: list[list] | None) -> None:
        """
        Enqueue any pending data, then wait for the queue to drain.

        If csv_path and rows are provided, enqueues a final save before waiting
        (for debounced data that hasn't been enqueued yet).
        """
        if csv_path and rows is not None:
            self.enqueue_save(csv_path, rows)
        self._flush_event.clear()
        self._queue.put(_FLUSH_SENTINEL)
        self._flush_event.wait(timeout=5.0)
