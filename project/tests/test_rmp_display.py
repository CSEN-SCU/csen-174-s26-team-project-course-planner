from utils.rmp_display import professors_sorted_by_rating


def test_sorts_by_rating_desc_none_last():
    profs = [
        {"name": "Low", "rating": 2.0},
        {"name": "High", "rating": 4.9},
        {"name": "None", "rating": None},
    ]
    out = professors_sorted_by_rating(profs)
    assert [p["name"] for p in out] == ["High", "Low", "None"]


def test_skips_non_dict_entries():
    out = professors_sorted_by_rating([{"name": "A", "rating": 3}, "skip", None])
    assert len(out) == 1 and out[0]["name"] == "A"
