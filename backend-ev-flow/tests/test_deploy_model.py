"""The refusals that stop a stale model reaching a deployed API.

Copying a file is the easy half of a deploy. The half that matters is not
copying the wrong one, and the wrong one does not announce itself: sklearn
serves a model fitted on data that has since moved without complaint, returning
confident, well-formed, wrong numbers. That is the same failure the feature-order
check in services/siting_model.py exists to prevent, one level up.

These cover the pure comparison. The copy, the restart and the /health probe need
a host and are exercised by running the script.
"""
import pytest

from scripts.deploy_model import ENV_FOR, artifact_fingerprint, compare


def _fp(cells=28176, stations=1197, connectors=3362, built="2026-08-26T00:11:00+00:00"):
    return {"cells": cells, "stations": stations, "connectors": connectors,
            "cells_built_at": built}


def test_identical_data_is_not_drift():
    assert compare(_fp(), _fp()) == []


def test_a_reloaded_grid_is_caught_by_its_timestamp():
    # The count can be identical after a reload while every value inside changed:
    # this is exactly what happened when lu_commercial_share was corrected for
    # 657 of 28,176 cells and the row count did not move.
    drift = compare(_fp(built="2026-08-24T09:00:00+00:00"), _fp())
    assert len(drift) == 1 and "cells_built_at" in drift[0]


def test_a_supply_refresh_is_caught():
    # nearest_station_m and stations_2km are recomputed from stations and
    # connectors, so a station import moves features no model can see changing.
    drift = compare(_fp(stations=1197), _fp(stations=1240))
    assert len(drift) == 1 and "stations" in drift[0]


def test_every_drifted_field_is_named_not_just_the_first():
    # A deploy refusal is read once. It has to say everything that moved, or the
    # second run refuses again for a reason the first message did not mention.
    drift = compare(_fp(cells=27219, stations=1100), _fp())
    assert len(drift) == 2


def test_a_timestamp_differing_only_in_sub_second_precision_is_not_drift():
    # Postgres returns microseconds; the artifact records isoformat. Comparing
    # the full string would refuse every deploy for a difference that is not one.
    assert compare(_fp(built="2026-08-26T00:11:00+00:00"),
                   _fp(built="2026-08-26T00:11:00.481922+00:00")) == []


def test_an_artifact_without_a_fingerprint_is_refused_not_defaulted(tmp_path):
    import joblib
    p = tmp_path / "siting_model.joblib"
    joblib.dump({"model": None, "feature_names": [], "trained_at": "x"}, p)
    with pytest.raises(SystemExit, match="no dataset_fingerprint"):
        artifact_fingerprint(p)


def test_only_filenames_a_service_actually_reads_are_deployable():
    # A renamed artifact would otherwise be copied to a path nothing loads, and
    # the API would keep answering 503 with the file sitting right there.
    assert set(ENV_FOR) == {"siting_model.joblib", "utilisation_model.joblib"}
