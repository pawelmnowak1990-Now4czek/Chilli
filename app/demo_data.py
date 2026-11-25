"""The demo data for `python -m app.demo_seed`: three projects and fifteen saves.

Everything here is made up to show what Chilli does: the titles, summaries and texts are written
for the demo, and the URLs point at well-known public sites only as plausible sources. No real
person or private data. The mix covers what the MCP tools show: search, top_saves (ratings per
project), from_archive (two saves 3-6 weeks old, rated 7+, still 'nowy'), due_reminders (one save),
different statuses, and one unrated save.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DemoProject:
    name: str
    description: str


@dataclass(frozen=True)
class DemoSave:
    title: str
    source_type: str  # screenshot, link or text (CHECK in db/schema.sql)
    kind: str  # one of the stored values: pomysł, artykuł, narzędzie, produkt, inne
    summary: str
    content_text: str
    tags: list[str]
    days_ago: int
    url: str | None = None
    source_app: str | None = None
    status: str = "nowy"
    # Project name -> (score 1-10, reason). Empty = an unrated save.
    ratings: dict[str, tuple[int, str]] = field(default_factory=dict)
    # Reminder due yesterday, so due_reminders shows it.
    reminder_due: bool = False


GARDEN = "Demo: Balcony garden"
APP = "Demo: Indie app launch"
SQL = "Demo: SQL skills"

PROJECTS = [
    DemoProject(GARDEN, "Growing vegetables and herbs on a small city balcony: containers, watering, light."),
    DemoProject(APP, "Launching a small paid Mac app: landing page, pricing, App Store screenshots, first users."),
    DemoProject(SQL, "Getting better at analytical SQL: window functions, query plans, data modelling."),
]

SAVES = [
    DemoSave(
        title="Window functions, explained with one sales table",
        source_type="link", kind="artykuł", days_ago=2,
        url="https://www.postgresql.org/docs/current/tutorial-window.html", source_app="PostgreSQL docs",
        summary="A walk-through of ROW_NUMBER, RANK and running totals over one example table. "
                "Useful as a reference for picking the latest row per customer without self-joins.",
        content_text="Window functions compute a value for each row from a set of related rows. "
                     "ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY ordered_at DESC) numbers each "
                     "customer's orders, so filtering on 1 keeps the latest. SUM(amount) OVER (ORDER BY day) "
                     "gives a running total.",
        tags=["sql", "window functions", "postgres"],
        ratings={SQL: (9, "Exactly the pattern for latest-row-per-key queries in reports.")},
    ),
    DemoSave(
        title="EXPLAIN ANALYZE cheat sheet: what to look at first",
        source_type="screenshot", kind="artykuł", days_ago=5, source_app="X", status="przejrzany",
        summary="A screenshot of a short thread on reading query plans: compare estimated and actual rows, "
                "look for sequential scans on big tables, check the slowest node first.",
        content_text="Reading a plan in 3 steps: 1. find the node with the largest actual time. "
                     "2. compare rows= estimate with actual rows; a 100x gap means stale statistics. "
                     "3. Seq Scan on a large table inside a loop is the usual suspect.",
        tags=["sql", "query plans", "performance"],
        ratings={SQL: (8, "A checklist for tuning slow dashboard queries.")},
    ),
    DemoSave(
        title="Self-watering planter from two buckets",
        source_type="screenshot", kind="pomysł", days_ago=1, source_app="Instagram",
        summary="A picture of a DIY self-watering container: an inner bucket with holes, a wicking cup and a "
                "water reservoir below. A cheap way to survive a week away in summer.",
        content_text="Two food-safe buckets, a net cup, a fill pipe. Drill holes in the inner bucket, "
                     "put the net cup through the bottom as a wick, fill the outer bucket through the pipe.",
        tags=["diy", "watering", "containers"],
        ratings={GARDEN: (8, "Solves watering during the summer holidays.")},
    ),
    DemoSave(
        title="Growing tomatoes in pots: varieties and spacing",
        source_type="link", kind="artykuł", days_ago=26,
        url="https://www.rhs.org.uk/vegetables/tomatoes/grow-your-own", source_app="RHS",
        summary="A guide to tomatoes in containers: bush varieties for small spaces, pot sizes, feeding "
                "and when to start seeds indoors.",
        content_text="Choose bush (determinate) varieties for pots of at least 30 litres. Start seeds indoors "
                     "six to eight weeks before the last frost. Feed weekly once the first flowers appear.",
        tags=["tomatoes", "containers", "seeds"],
        ratings={GARDEN: (9, "The core plan for this season's balcony crop.")},
    ),
    DemoSave(
        title="Pricing page teardown: three tiers that convert",
        source_type="link", kind="artykuł", days_ago=38,
        url="https://www.indiehackers.com/", source_app="Indie Hackers",
        summary="A breakdown of small-software pricing pages: one plan highlighted, annual discount shown "
                "as months free, and a plain list of what each tier adds.",
        content_text="Three tiers, the middle one highlighted. Show the annual price as 2 months free. "
                     "List differences, not everything. Put a short FAQ about refunds under the table.",
        tags=["pricing", "landing page", "saas"],
        ratings={APP: (8, "A template for the pricing section of the landing page.")},
    ),
    DemoSave(
        title="App Store screenshot sizes for Mac apps",
        source_type="link", kind="artykuł", days_ago=3, reminder_due=True,
        url="https://developer.apple.com/help/app-store-connect/reference/screenshot-specifications",
        source_app="Apple Developer",
        summary="The accepted screenshot sizes and counts for Mac App Store listings, with notes on "
                "aspect ratios and text overlays.",
        content_text="Mac apps need at least one screenshot in a 16:10 size such as 2880 x 1800. Up to ten "
                     "screenshots per localisation. Keep text large enough to read at thumbnail size.",
        tags=["app store", "screenshots", "mac"],
        ratings={APP: (7, "Needed before submitting the first build.")},
    ),
    DemoSave(
        title="Plausible: simple, cookie-free web analytics",
        source_type="link", kind="narzędzie", days_ago=4, status="wykorzystany",
        url="https://plausible.io/", source_app="Plausible",
        summary="A lightweight analytics tool without cookies, with one dashboard for visitors, sources "
                "and goals. A privacy-friendly option for a small landing page.",
        content_text="One script tag, no cookie banner needed. Shows visitors, top pages, referrers and "
                     "custom goals such as 'download clicked'.",
        tags=["analytics", "privacy", "landing page"],
        ratings={APP: (6, "Analytics for the landing page without a cookie banner.")},
    ),
    DemoSave(
        title="Drip irrigation starter kit for balconies",
        source_type="link", kind="produkt", days_ago=6,
        url="https://www.gardena.com/", source_app="Gardena",
        summary="A small drip system with a timer for up to 15 pots, connected to an outdoor tap.",
        content_text="Starter set: timer, 15 drippers, 10 m pipe, connectors. Each dripper adjustable "
                     "from 0 to 4 litres per hour.",
        tags=["watering", "irrigation", "product"],
        ratings={GARDEN: (7, "An alternative to the DIY planter for the whole balcony.")},
    ),
    DemoSave(
        title="Incremental models: only process new rows",
        source_type="screenshot", kind="artykuł", days_ago=7, source_app="LinkedIn",
        summary="A post about incremental loads in a warehouse: filter on an updated_at watermark and "
                "merge on a unique key, so nightly runs stay fast.",
        content_text="Incremental pattern: WHERE updated_at > (SELECT max(updated_at) FROM target), then "
                     "MERGE on the business key. Rebuild fully once a week to catch late changes.",
        tags=["data modelling", "incremental", "warehouse"],
        ratings={SQL: (6, "Relevant for the nightly reporting tables.")},
    ),
    DemoSave(
        title="Launch week checklist",
        source_type="text", kind="pomysł", days_ago=8, status="przejrzany",
        url="https://news.ycombinator.com/", source_app="Hacker News",
        summary="A selected comment with a launch-week plan: soft launch to a mailing list, then a public "
                "post, then a follow-up with what was learned.",
        content_text="Day 1: email the waiting list. Day 3: public post with a short demo video. "
                     "Day 7: write up the numbers and what you would change.",
        tags=["launch", "checklist", "marketing"],
        ratings={APP: (9, "The plan to follow in the launch week.")},
    ),
    DemoSave(
        title="Does planting by the moon work?",
        source_type="link", kind="artykuł", days_ago=9,
        url="https://en.wikipedia.org/wiki/Lunar_effect", source_app="Wikipedia",
        summary="An overview of claims about the moon's effect on living things, and what studies found.",
        content_text="Many traditions time sowing by lunar phases. Controlled studies have not found a "
                     "reliable effect on germination or yield.",
        tags=["myths", "science", "sowing"],
        ratings={GARDEN: (2, "Interesting, but nothing to act on.")},
    ),
    DemoSave(
        title="explain.dalibo.com: paste a plan, get a diagram",
        source_type="link", kind="narzędzie", days_ago=10, status="wykorzystany",
        url="https://explain.dalibo.com/", source_app="Dalibo",
        summary="A web tool that turns a PostgreSQL EXPLAIN output into a readable tree with the slow "
                "nodes highlighted.",
        content_text="Paste the output of EXPLAIN (ANALYZE, BUFFERS) and get a visual plan with timings "
                     "per node and warnings for misestimates.",
        tags=["postgres", "query plans", "tool"],
        ratings={SQL: (8, "Makes plan reviews faster.")},
    ),
    DemoSave(
        title="Basil keeps flowering: pinch the tops",
        source_type="screenshot", kind="inne", days_ago=11, source_app="Safari",
        summary="A screenshot of a gardening answer: pinch off flower buds and the top pair of leaves "
                "every week to keep basil bushy.",
        content_text="Pinch above a pair of leaves, remove flower buds as soon as they appear, water "
                     "in the morning, and keep it out of cold wind.",
        tags=["herbs", "basil", "care"],
        ratings={GARDEN: (5, "A small care tip for the herbs.")},
    ),
    DemoSave(
        title="A short email to recruit beta testers",
        source_type="screenshot", kind="pomysł", days_ago=12, source_app="X",
        summary="A template for asking people to try an early version: one line on the problem, one on "
                "what you need, and a clear way to say no.",
        content_text="Hi, I am building a small Mac app for X. Would you try it for 10 minutes and tell me "
                     "what confused you? No worries if not.",
        tags=["beta", "email", "users"],
        ratings={APP: (6, "Wording for the first beta invites.")},
    ),
    DemoSave(
        title="Low-profile mechanical keyboard on sale",
        source_type="link", kind="produkt", days_ago=2,
        url="https://www.amazon.com/", source_app="Amazon",
        summary="A deal on a compact wireless keyboard. Saved on impulse; not related to any project.",
        content_text="75% layout, low-profile switches, Bluetooth and USB-C.",
        tags=["keyboard", "deal"],
    ),
]
