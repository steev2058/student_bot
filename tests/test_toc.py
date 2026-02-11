from app.ingest.toc_extractor import validate_toc_targets


def test_validate_toc_targets():
    toc = [{"title": "درس", "printed_page": 10}]
    m = {10: 20}
    v = validate_toc_targets(toc, m)
    assert v[0]["pdf"] == 20
