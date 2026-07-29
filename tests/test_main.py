from rag_finalize.__main__ import build_parser


def test_run_id_is_optional():
    args = build_parser().parse_args([])
    assert args.run_id is None  # None → whole-table mode


def test_parser_accepts_run_id():
    args = build_parser().parse_args(["--run-id", "r1"])
    assert args.run_id == "r1"
