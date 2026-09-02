from plot_density_margin_selection import margin_rows


def test_margin_rows_orders_by_release_margin():
    rows = margin_rows(
        [
            {"compression_release_margin": 0.55},
            {"compression_release_margin": 0.18},
            {"compression_release_margin": 0.35},
        ]
    )

    assert [row["compression_release_margin"] for row in rows] == [0.18, 0.35, 0.55]
