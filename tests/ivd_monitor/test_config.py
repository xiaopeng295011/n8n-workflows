from pathlib import Path

import pytest

from src.ivd_monitor.config import IVDConfig


def test_config_loads_sources():
    config_path = Path(__file__).parent.parent.parent / "config" / "ivd_sources.yaml"
    config = IVDConfig(config_path)

    enabled = config.get_enabled_sources()
    assert len(enabled) > 0

    source_ids = {src.source_id for src in enabled}
    assert "financial.cninfo_juchao" in source_ids
    assert "regulatory.nmpa_approvals" in source_ids


def test_get_source_metadata():
    config_path = Path(__file__).parent.parent.parent / "config" / "ivd_sources.yaml"
    config = IVDConfig(config_path)

    juchao = config.get_source("financial.cninfo_juchao")
    assert juchao is not None
    assert juchao.source_type == "financial_reports"
    assert juchao.enabled is True
    assert juchao.page_size == 30

    nmpa = config.get_source("regulatory.nmpa_approvals")
    assert nmpa is not None
    assert nmpa.source_type == "product_launches"
    assert nmpa.page_size == 20


def test_get_settings():
    config_path = Path(__file__).parent.parent.parent / "config" / "ivd_sources.yaml"
    config = IVDConfig(config_path)

    timeout = config.get_setting("default_timeout_seconds", 10)
    assert timeout == 20

    user_agent = config.get_setting("user_agent")
    assert "IVDMonitor" in user_agent


def test_get_category_info():
    config_path = Path(__file__).parent.parent.parent / "config" / "ivd_sources.yaml"
    config = IVDConfig(config_path)

    cat = config.get_category_info("financial_reports")
    assert "Financial Reports" in cat["display_name"]

    policy_cat = config.get_category_info("reimbursement_policy")
    assert policy_cat["display_name"] == "Reimbursement Policy"
