"""Två rör som kopplas ihop är inte en hänvisning.

Regeln hela läsningen står på är att en beteckning får sitt rör av den linje ritaren faktiskt drog, aldrig av
vad som råkar ligga nära. Fyra kontaktsorter är undantag från bokstaven i den regeln, och de behövs: en ledare
som slutar i ett stigarmärke, en ändcirkel, en liten armatur eller på en samlingslinje pekar ut röret genom
märket. De är bryggor, och de står redan uppräknade som svaga (WEAK_KINDS).

Men en brygga som landar där flera rör kopplas ihop lämnade ifrån sig allihop. Då var det kopplingen mellan
rören - rör-mot-rör-kontakten - som gav namnet, inte hänvisningslinjen, och etiketten ägde två stråk som
ritaren aldrig pekat ut mer än ett av.

Skillnaden är ritad och går att läsa, men bara delvis. En brygga mitt på ett stråk rör samma rör åt två håll,
och de två sträckorna ligger på samma linje - ett rör. Tre eller fler armar i punkten är en gren eller en knut,
och där säger ingenting vilken av dem etiketten menar.

Två armar som möts i vinkel är däremot inte avgjort, och därför frågas det inte: ett rör som svänger runt ett
hörn ser precis likadant ut som två rör som kopplas ihop där. Att fråga i det läget mättes mot alla 59 blad och
kostade 2,5 procentenheters täckning för 1,7 i falskt ägande - fler riktiga meter förlorade än falska. Att
fråga bara vid tre armar kostade 0,6 och gav 0,8 i precision och sex färre felaktiga rader. Gränsen ligger
alltså där mätningen lade den, inte där resonemanget först ville ha den.

En riktig ledarände ställs aldrig som en fråga, hur många rör som än möts där: då pekade ritaren.
"""
from vvs_engine.geometry.core import Seg
from vvs_engine.pdf.extract import RawPath
from vvs_engine.semantics.attachment import Contact, _bridge_spread, _distinct_runs


def _path(pid: str, *pts: tuple[float, float]) -> RawPath:
    segs = [Seg(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1]) for i in range(len(pts) - 1)]
    return RawPath(pid=pid, seqno=0, page=0, layer="V-ROR", layer_id=None, kind="s", width=0.5,
                   color=(0, 0, 0), fill=None, closed=False, segs=segs,
                   bbox=(min(p[0] for p in pts), min(p[1] for p in pts),
                         max(p[0] for p in pts), max(p[1] for p in pts)),
                   n_items=1, n_curves=0, n_subpaths=1)


def _bridge(*pids: str) -> list[Contact]:
    return [Contact(point=(10.0, 0.0), kind="via_marker", family="V-ROR|s|0.5", pid=pid, seg_index=0,
                    distance=0.1) for pid in pids]


def test_a_marker_in_the_middle_of_one_run_is_one_pipe():
    """Röret fortsätter genom märket: två kontakter, en linje, ett rör - ingen fråga."""
    paths = {"a": _path("a", (0, 0), (10, 0)), "b": _path("b", (10, 0), (20, 0))}
    assert _distinct_runs(_bridge("a", "b"), paths) == 1
    assert _bridge_spread(_bridge("a", "b"), paths) == 1


def test_a_corner_is_a_bend_and_is_not_asked_about():
    """Två armar i vinkel: geometriskt två sträckor, men ett rör som svänger ser likadant ut. Ingen fråga."""
    paths = {"a": _path("a", (0, 0), (10, 0)), "b": _path("b", (10, 0), (10, 10))}
    assert _distinct_runs(_bridge("a", "b"), paths) == 2
    assert _bridge_spread(_bridge("a", "b"), paths) == 1


def test_three_arms_in_the_marker_is_a_question():
    """En knut: tre rör möts. Ritaren drog en linje till ett av dem, och bladet säger inte vilket."""
    paths = {"a": _path("a", (0, 0), (10, 0)), "b": _path("b", (10, 0), (20, 0)),
             "c": _path("c", (10, 0), (10, 10)), "d": _path("d", (10, 0), (20, 10))}
    # a och b ligger på samma linje - röret som går rakt igenom knuten. c och d är två armar till.
    cs = _bridge("a", "b", "c", "d")
    assert _distinct_runs(cs, paths) == 3
    assert _bridge_spread(cs, paths) == 3


def test_two_parallel_pipes_in_one_marker_are_two_pipes():
    """Staplade ändmärken: rören lutar likadant men ligger bredvid varandra, och är två rör."""
    paths = {"a": _path("a", (0, 0), (10, 0)), "b": _path("b", (0, 4), (10, 4))}
    assert _distinct_runs(_bridge("a", "b"), paths) == 2


def test_a_real_leader_end_is_never_a_bridge():
    """Ledaren slutar PÅ röret. Det är det ritaren drog, och det ställs aldrig som en fråga."""
    paths = {"a": _path("a", (0, 0), (10, 0)), "b": _path("b", (10, 0), (10, 10))}
    ends = [Contact(point=(10.0, 0.0), kind="end", family="V-ROR|s|0.5", pid=p, seg_index=0, distance=0.1)
            for p in ("a", "b")]
    assert _bridge_spread(ends, paths) == 0
    # ...och en blandning där ledaren faktiskt rörde röret är inte heller en brygga
    assert _bridge_spread(ends[:1] + _bridge("b"), paths) == 0
