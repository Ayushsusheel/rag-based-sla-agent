import logging
import time
from contextlib import contextmanager

from rich.logging import RichHandler

from app.config import LOG_DIR

LOGGER_NAME = "ms_sla_prod"
LOG_FILE = LOG_DIR / "ms_sla_prod.log"


def get_logger():
    logger = logging.getLogger(LOGGER_NAME)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    logger.propagate = False

    rich_handler = RichHandler(
        rich_tracebacks=True,
        markup=True,
        show_path=False,
        show_time=True,
    )
    rich_handler.setLevel(logging.INFO)
    rich_handler.setFormatter(logging.Formatter("%(message)s"))

    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    )

    logger.addHandler(rich_handler)
    logger.addHandler(file_handler)
    return logger


logger = get_logger()


@contextmanager
def log_step(step: str, **kwargs):
    meta = " ".join(f"{k}={v}" for k, v in kwargs.items())
    logger.info(f"[bold cyan]START[/] {step} {meta}".strip())
    start = time.perf_counter()
    try:
        yield
        elapsed = time.perf_counter() - start
        logger.info(f"[bold green]END[/] {step} elapsed={elapsed:.2f}s")
    except Exception as e:
        elapsed = time.perf_counter() - start
        logger.exception(f"[bold red]FAIL[/] {step} elapsed={elapsed:.2f}s error={e}")
        raise