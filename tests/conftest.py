from __future__ import annotations

import pytest

from naim_risk.config import load_config
from naim_risk.pipeline import run_pipeline
from naim_risk.service import WorkbenchService


@pytest.fixture(scope="session")
def test_config(tmp_path_factory: pytest.TempPathFactory):
    return load_config("test", data_root=tmp_path_factory.mktemp("naim-data"))


@pytest.fixture(scope="session")
def pipeline_data(test_config):
    return run_pipeline(test_config, persist=False)


@pytest.fixture(scope="session")
def service(test_config, pipeline_data):
    return WorkbenchService(test_config, pipeline_data)
