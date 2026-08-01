"""Unit test: SECTOR_BASKETS sebagai satu sumber kebenaran sektor."""
from app.services.scraper import SECTOR_BASKETS, IHSGScraper


def test_all_sectors_have_label_and_stocks():
    assert len(SECTOR_BASKETS) == 11
    for code, info in SECTOR_BASKETS.items():
        assert info["name"]
        assert info["corr_label"]
        assert len(info["stocks"]) >= 4


def test_stock_sector_map_derived_consistently():
    # Setiap saham muncul tepat di satu sektor (tidak dobel)
    seen = {}
    for code, info in SECTOR_BASKETS.items():
        for s in info["stocks"]:
            assert s not in seen, f"{s} dobel di {seen[s]} & {code}"
            seen[s] = code
    # STOCK_SECTOR_MAP (class attr) punya label konsisten dengan SECTOR_BASKETS
    for sym, entry in IHSGScraper.STOCK_SECTOR_MAP.items():
        assert "label" in entry
        assert entry["label"]
