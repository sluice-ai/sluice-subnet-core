from typing import Optional

import bittensor as bt
import numpy as np

from sluice.models import RoutingExecutionReport, RoutingTask
from sluice.scorer import score_many, score_one


def reward(
    report: Optional[RoutingExecutionReport],
    task: RoutingTask,
) -> float:
    score = score_one(report, task)
    bt.logging.info(
        f"reward -> provider={report.selected_provider_id if report else 'N/A'} score={score:.4f}"
    )
    return score


def get_rewards(
    self,
    reports: list[Optional[RoutingExecutionReport]],
    task: RoutingTask,
) -> np.ndarray:
    scores = score_many(reports, task)
    bt.logging.info(
        f"get_rewards -> n={len(scores)} mean={np.mean(scores):.4f} "
        f"max={np.max(scores):.4f} nonzero={np.count_nonzero(scores)}"
    )
    return scores
