import pytest

from rag_finalize.__main__ import build_parser


def test_run_id_is_required():
    # argparse exits 2 — the stage's usage-error code
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args([])
    assert exc.value.code == 2


def test_parser_accepts_run_id():
    args = build_parser().parse_args(["--run-id", "r1"])
    assert args.run_id == "r1"
