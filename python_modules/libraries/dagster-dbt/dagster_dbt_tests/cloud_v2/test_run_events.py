from dagster import AssetCheckEvaluation, AssetMaterialization
from dagster_dbt.cloud_v2.run_handler import DbtCloudJobRunResults
from dagster_dbt.cloud_v2.types import DbtCloudWorkspaceData

from dagster_dbt_tests.cloud_v2.conftest import get_sample_run_results_json


def test_default_asset_events_from_run_results(workspace_data: DbtCloudWorkspaceData):
    run_results = DbtCloudJobRunResults.from_run_results_json(
        run_results_json=get_sample_run_results_json()
    )

    events = [event for event in run_results.to_default_asset_events(workspace_data=workspace_data)]

    asset_materializations = [event for event in events if isinstance(event, AssetMaterialization)]
    asset_check_evaluations = [event for event in events if isinstance(event, AssetCheckEvaluation)]

    # 8 asset materializations
    assert len(asset_materializations) == 8
    # 20 asset check evaluations
    assert len(asset_check_evaluations) == 20

    # Sanity check
    first_mat = next(mat for mat in sorted(asset_materializations))
    assert first_mat.asset_key.path == ["customers"]

    first_check_eval = next(check_eval for check_eval in sorted(asset_check_evaluations))
    assert first_check_eval.check_name == "not_null_customers_customer_id"
    assert first_check_eval.asset_key.path == ["customers"]
