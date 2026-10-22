"""Authored synthetic fixtures, not user data or model responses."""

import csv
from . import db
from .media import make_demo, probe, replace_segment
from .research import CSV_COLUMNS, gen_brief, evaluate


def seed():
    db.init()
    wid = "demo-coffee"
    with db.connect() as c:
        if c.execute("SELECT 1 FROM workspaces WHERE id=?", (wid,)).fetchone():
            print("Demo already exists; history preserved.")
            return
        prior = c.execute(
            "SELECT id FROM users WHERE email=?", ("demo@example.test",)
        ).fetchone()
        owner = prior[0] if prior else db.uid()
        if not prior:
            c.execute(
                "INSERT INTO users VALUES(?,?,?)",
                (owner, "demo@example.test", db.password("creative-demo")),
            )
        brand = dict(
            id=wid,
            name="Daybreak Coffee",
            product="Small-batch coffee for everyday rituals",
            audience="Home coffee enthusiasts",
            goal="Find the next opening to test",
            synthetic=True,
        )
        c.execute("INSERT INTO workspaces VALUES(?,?,?)", (wid, owner, db.pack(brand)))
    folder = db.ROOT / wid
    folder.mkdir(parents=True, exist_ok=True)
    metrics = []
    for i, (hook, retention) in enumerate(
        [
            ("packaging", 0.40),
            ("packaging", 0.44),
            ("preparation", 0.56),
            ("preparation", 0.60),
        ],
        1,
    ):
        vid = f"demo-video-{i}"
        path = folder / (vid + ".mp4")
        make_demo(path, hook=hook, duration=8)
        m = probe(path)
        analysis = dict(
            mode="synthetic_fixture",
            model=None,
            prompt_version="authored-fixture-v1",
            measured=m,
            hook_category=hook,
            speech_status="not_transcribed",
            limitations=[
                "Authored synthetic demonstration; annotations are fixture labels, not model inference."
            ],
            segments=[
                dict(
                    start=0,
                    end=2,
                    kind="hook",
                    text=(
                        "Coffee preparation opening"
                        if hook == "preparation"
                        else "Coffee packaging opening"
                    ),
                    origin="fixture",
                ),
                dict(
                    start=2,
                    end=6,
                    kind="product",
                    text="Coffee product demonstration",
                    origin="fixture",
                ),
                dict(
                    start=6,
                    end=8,
                    kind="cta",
                    text="Closing product card",
                    origin="fixture",
                ),
            ],
        )
        value = dict(
            id=vid,
            title=f'{"Pour first" if hook=="preparation" else "Pack first"} / {i:02d}',
            filename=path.name,
            path=str(path),
            synthetic=True,
            analysis=analysis,
            **m,
            created_at=db.now(),
        )
        row = dict(
            id=db.uid(),
            publication_id=f"synthetic-post-{i}",
            video_id=vid,
            platform="instagram",
            traffic="organic",
            source="synthetic-demo-v1",
            period_start="2026-10-01",
            period_end="2026-10-08",
            views=1000,
            retention_3s=retention,
            retention_unit="fraction",
            imported_at=db.now(),
        )
        metrics.append(row)
        with db.connect() as c:
            db.save(c, wid, "video", value)
            db.save(c, wid, "metric", row)
    replacement = folder / "replacement.mp4"
    make_demo(replacement, hook="preparation", duration=2)
    variant = folder / "demo-past-variant.mp4"
    report = replace_segment(folder / "demo-video-1.mp4", replacement, 0, 2, variant)
    variant_id = "demo-past-variant"
    v = dict(
        id=variant_id,
        title="Previous opening test / no improvement",
        filename=variant.name,
        path=str(variant),
        synthetic=True,
        analysis=None,
        **probe(variant),
        created_at=db.now(),
    )
    metric = dict(
        metrics[0],
        id=db.uid(),
        video_id=variant_id,
        publication_id="synthetic-past-variant",
        retention_3s=0.39,
    )
    e = dict(
        id="demo-past-experiment",
        title="Previous pour-first test",
        hypothesis="A preparation opening improves three-second retention.",
        baseline_id="demo-video-1",
        variant_id=variant_id,
        change="Replace first two seconds with coffee preparation",
        preserve=["Original soundtrack", "Remaining six seconds", "Offer", "Duration"],
        metric="retention_3s",
        threshold_pp=5,
        min_views=100,
        window_days=7,
        limitations=["Entire example and metrics are synthetic."],
        status="completed",
        revision=1,
        created_at=db.now(),
        edit_report=report,
    )
    e["frozen_criteria"] = {
        k: e[k]
        for k in (
            "hypothesis",
            "threshold_pp",
            "min_views",
            "window_days",
            "metric",
            "revision",
        )
    }
    e["generation_brief"] = gen_brief(e)
    e["result"] = evaluate(e, [metrics[0]], [metric])
    e["result"].update(synthetic=True, evaluated_at=db.now())
    e["history"] = [
        dict(
            at=db.now(),
            action="synthetic_example_seeded",
            note="Not a real published experiment",
            result=e["result"],
        )
    ]
    with db.connect() as c:
        db.save(c, wid, "video", v)
        db.save(c, wid, "metric", metric)
        db.save(c, wid, "experiment", e)
    with (folder / "metrics.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(metrics)
    print("Synthetic demo ready: demo@example.test / creative-demo")


if __name__ == "__main__":
    seed()
