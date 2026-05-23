import os
import sys
from pathlib import Path

import bittensor as bt

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sluice_subnet.base.validator import BaseValidatorNeuron
from sluice_subnet.validator import forward
from sluice_subnet.validator.forward import sandbox


class Validator(BaseValidatorNeuron):
    def __init__(self, config=None):
        super().__init__(config=config)

        should_build_sandbox = (
            os.getenv("SLUICE_SKIP_SANDBOX_BUILD", "0") != "1" and not self.config.mock
        )
        if should_build_sandbox:
            sandbox_dir = Path(__file__).resolve().parent.parent / "agent"
            bt.logging.info(f"Building Sluice sandbox image from {sandbox_dir}")
            sandbox.build_image(str(sandbox_dir))
        else:
            bt.logging.info("Skipping Sluice sandbox build")

        self.load_state()

    async def forward(self):
        return await forward(self)


def main():
    validator = Validator()
    validator.run()


if __name__ == "__main__":
    main()
