from __future__ import annotations

import threading
import traceback

import streamlit as st
from streamlit_folium import st_folium

from agents.base import LLMClient
from agents.graph import run_pipeline
from agents.transport_agent import StopNotFoundError
from models.journey import Mode
from models.route import JourneyRequest
from services.maps_api import build_map
from utils.geo import format_distance, format_minutes, format_money


# ============================================================
# CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="TransitAI",
    page_icon="🚌",
    layout="wide",
)

MODE_OPTIONS = [
    ("metro", "Metro"),
    ("bus", "Bus"),
    ("train", "Train"),
]

PROFILES = [
    "balanced",
    "fastest",
    "cheapest",
    "fewest_transfers",
    "most_reliable",
]

EXAMPLE = (
    "I need to reach HITEC City from LB Nagar tomorrow before 9 AM. "
    "Keep the fare below ₹100 and avoid more than one transfer."
)


# ============================================================
# SESSION STATE
# ============================================================

# Store the most recent planning result.
# Streamlit reruns the entire script whenever a widget changes,
# so session_state is required to keep the result alive.
if "output" not in st.session_state:
    st.session_state.output = None

# Store the last request so we know what was planned.
if "last_request" not in st.session_state:
    st.session_state.last_request = None

# Prevent duplicate cache-warming threads.
if "warm_started" not in st.session_state:
    st.session_state.warm_started = False


# ============================================================
# LLM
# ============================================================

llm = LLMClient()


# ============================================================
# CACHE WARMING
# ============================================================

def _warm_caches() -> None:
    """
    Warm graph and RAG caches in the background.

    This prevents the first planning request from having to
    initialize everything from scratch.
    """

    if st.session_state.warm_started:
        return

    st.session_state.warm_started = True

    def build() -> None:
        try:
            from rag.retriever import get_retriever
            from services import get_graph

            get_graph()
            get_retriever()

        except Exception:
            # Cache warming should never crash the application.
            pass

    threading.Thread(
        target=build,
        daemon=True,
    ).start()


_warm_caches()


# ============================================================
# HELPERS
# ============================================================

def parse_time_input(value: str) -> str | None:
    """
    Validate a HH:MM 24-hour time input.
    """

    value = (value or "").strip()

    if not value:
        return None

    parts = value.split(":")

    if len(parts) != 2:
        return None

    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError:
        return None

    if 0 <= hour <= 23 and 0 <= minute <= 59:
        return f"{hour:02d}:{minute:02d}"

    return None


def journey_row(graph, evaluated, rank: int) -> dict:
    """
    Convert an evaluated journey into a table row.
    """

    journey = evaluated.journey

    total_dist = sum(l.distance_m for l in journey.legs)
    return {
        "Rank": rank,
        "Journey": journey.summary,
        "Depart": journey.depart_at,
        "Arrive": journey.arrive_at,
        "Distance": f"{total_dist/1000.0:.2f} km",
        "Time": format_minutes(journey.duration_min),
        "Fare": format_money(journey.fare),
        "Fare/km": f"{(journey.fare/(total_dist/1000.0)):.2f}/km" if total_dist > 0 else "-",
        "Transfers": journey.transfers,
        "Walking": format_distance(journey.walk_m),
        "Reliability": f"{journey.reliability * 100:.0f}%",
        "Score": f"{evaluated.score:.3f}",
        "Delay (live)": (
            f"{journey.live_delay_min:.0f} min"
            if journey.live_delay_min
            else "none"
        ),
    }


def render_journey_table(graph, evaluated) -> None:
    """
    Render alternative journeys.
    """

    rows = []

    for rank_offset, item in enumerate(evaluated, start=1):
        rows.append(
            journey_row(
                graph,
                item,
                rank_offset,
            )
        )

    if rows:
        st.dataframe(
            rows,
            width="stretch",
            hide_index=True,
        )


# ============================================================
# RESULT RENDERING
# ============================================================

def render(output) -> None:
    """
    Render the complete planning result.

    This function receives the stored pipeline output and does
    not execute the pipeline itself.
    """

    if output is None:
        return

    graph = output.transport.graph
    live = output.transport.live

    # --------------------------------------------------------
    # LIVE DATA STATUS
    # --------------------------------------------------------

    if live.source == "live":
        st.success(
            f"Live transit feed (genuine) applied — updated {live.updated_at}."
        )

    elif live.source == "simulated":
        st.warning(
            "Simulated live disruptions (demo) applied to this plan."
        )

    else:
        st.info(
            "Live feed unavailable (demo/static) — results use the latest "
            "static schedule."
        )

    for message in live.messages:
        st.caption("• " + message)

    # --------------------------------------------------------
    # NO ROUTE FOUND
    # --------------------------------------------------------

    if not output.evaluated:
        st.warning(
            output.recommendation.explanation
        )
        return

    # --------------------------------------------------------
    # RECOMMENDED JOURNEY
    # --------------------------------------------------------

    by_origin_dest = (
        f"from **{output.transport.origin_name}** "
        f"to **{output.transport.dest_name}**"
    )

    st.subheader(
        f"Recommended journey {by_origin_dest}"
    )

    st.write(
        output.recommendation.explanation
    )

    # Recommendation warnings
    for warning in output.recommendation.warnings:
        st.caption(
            "⚠️ " + warning
        )

    best = output.recommendation.best

    # --------------------------------------------------------
    # METRICS
    # --------------------------------------------------------

    m1, m2, m3, m4, m5 = st.columns(5)

    m1.metric(
        "Time",
        format_minutes(best.journey.duration_min),
    )

    m2.metric(
        "Fare",
        format_money(best.journey.fare),
    )

    m3.metric(
        "Transfers",
        best.journey.transfers,
    )

    m4.metric(
        "Walking",
        format_distance(best.journey.walk_m),
    )

    m5.metric(
        "Reliability",
        f"{best.journey.reliability * 100:.0f}%",
    )

    total_dist_km = sum(l.distance_m for l in best.journey.legs) / 1000.0
    # Compute direct straight-line distance for comparison if available
    try:
        from utils.geo import haversine_m
        graph_obj = graph
        orig = graph_obj.stops.get(output.transport.origin_id)
        dest = graph_obj.stops.get(output.transport.dest_id)
        if orig and dest:
            direct_m = haversine_m(orig.lat, orig.lon, dest.lat, dest.lon)
            st.caption(f"Total distance (route): {format_distance(sum(l.distance_m for l in best.journey.legs))} ({total_dist_km:.2f} km) | Direct distance (as-the-crow-flies): {format_distance(direct_m)} ({direct_m/1000.0:.2f} km)")
        else:
            st.caption(f"Total distance: {format_distance(sum(l.distance_m for l in best.journey.legs))} ({total_dist_km:.2f} km)")
    except Exception:
        st.caption(f"Total distance: {format_distance(sum(l.distance_m for l in best.journey.legs))} ({total_dist_km:.2f} km)")

    st.divider()

    with st.expander("Route breakdown (with distances and fares)"):
        for i, leg in enumerate(best.journey.legs, start=1):
            d_km = leg.distance_m / 1000.0
            svc = leg.service_name if leg.service_id else "Walk"
            st.write(
                f"Leg {i}: {leg.mode.value.upper()} - {svc} - {leg.from_stop} -> {leg.to_stop} - {format_distance(leg.distance_m)} ({d_km:.2f} km) - Fare: {format_money(leg.fare)} - Time: {format_minutes(leg.duration_min)}"
            )
        total = sum(l.distance_m for l in best.journey.legs)
        st.caption(
            f"Total: {format_distance(total)} | {format_money(best.journey.fare)} | {format_minutes(best.journey.duration_min)}"
        )

    st.divider()

    # --------------------------------------------------------
    # MAP + ALTERNATIVES
    # --------------------------------------------------------

    left, right = st.columns(
        [3, 2],
        gap="large",
    )

    with left:

        st.markdown(
            "#### 🗺️ Journey on the map"
        )

        try:
            map_ = build_map(
                graph,
                output.transport.origin_id,
                output.transport.dest_id,
                output.evaluated,
            )

            st_folium(
                map_,
                width="100%",
                height=480,
                key="transit_map",
            )

        except Exception as exc:
            st.error(
                f"Unable to render map: {exc}"
            )

    with right:

        st.markdown(
            "#### 🔀 Alternatives"
        )

        if output.recommendation.alternatives:

            render_journey_table(
                graph,
                output.evaluated,
            )

            st.markdown(
                "**Why the alternatives ranked lower**"
            )

            if output.recommendation.comparisons:

                for line in output.recommendation.comparisons:
                    st.write(
                        "- " + line
                    )

        else:

            st.write(
                "No feasible alternatives found "
                "under your constraints."
            )

    if getattr(output, "rides", None):
        st.markdown("### Ride-hailing comparison (Rapido/Uber) — estimates only")
        st.caption("Prices shown are indicative estimates (not verified via provider APIs).")
        ride_rows = []
        for r in output.rides:
            ride_rows.append({
                "Provider": r.provider,
                "Mode": r.mode,
                "Fare (est.)": format_money(r.fare),
                "ETA (est.)": f"{r.eta_min:.1f} min",
                "Distance": format_distance(r.distance_m),
                "Surge": f"{r.surge:.2f}x",
            })
        st.dataframe(ride_rows, width="stretch", hide_index=True)

    # --------------------------------------------------------
    # SCORING BREAKDOWN
    # --------------------------------------------------------

    with st.expander(
        "Scoring breakdown"
    ):

        best_breakdown = best.breakdown

        st.write(
            "Penalty terms "
            "(0 = best, 1 = worst of the feasible set):"
        )

        st.json(
            {
                key: value
                for key, value in best_breakdown.items()
            }
        )

        st.caption(
            "Score = 1 − weighted sum of normalized penalties "
            "(time, cost, transfers, walking, unreliability). "
            "Higher is better."
        )

    # --------------------------------------------------------
    # RAG GROUNDING
    # --------------------------------------------------------

    with st.expander(
        "📚 RAG grounding (retrieved transport knowledge)"
    ):

        if output.chunks:

            for item in output.chunks:

                st.markdown(
                    f"**{item.chunk.source} — "
                    f"{item.chunk.heading}** "
                    f"(score {item.score:.2f})"
                )

                st.write(
                    item.chunk.text
                )

        else:

            st.write(
                "No knowledge-base documents retrieved "
                "for this request."
            )

    # --------------------------------------------------------
    # INTENT EXTRACTION
    # --------------------------------------------------------

    with st.expander(
        "🧠 Intent extraction"
    ):

        st.json(
            output.request.model_dump()
        )

        st.caption(
            f"Extraction source: {output.intent_source}. "
            + llm.label
        )

    # --------------------------------------------------------
    # RAW JOURNEY JSON
    # --------------------------------------------------------

    with st.expander(
        "🔧 Raw journey JSON"
    ):

        st.json(
            best.journey.model_dump()
        )


# ============================================================
# MAIN APPLICATION
# ============================================================

def main():

    # --------------------------------------------------------
    # HEADER
    # --------------------------------------------------------

    st.title("🚍 TransitAI")

    st.caption(
        "Agentic AI public transport route planning — "
        "Hyderabad sample network. Type a journey in natural "
        "language or fill the fields; the Intent Agent, RAG "
        "grounding, live status, and graph-based routing "
        "do the rest."
    )

    # --------------------------------------------------------
    # SIDEBAR
    # --------------------------------------------------------

    with st.sidebar:

        st.header("⚙️ Optimization")

        profile = st.selectbox(
            "Goal",
            PROFILES,
            index=0,
        )

        st.header("📋 Constraints")

        budget = st.number_input(
            "Maximum fare (₹)",
            min_value=0.0,
            max_value=2000.0,
            value=0.0,
            step=10.0,
            help="0 means no limit",
        )

        no_transfer_limit = st.checkbox(
            "No transfer limit",
            value=True,
        )

        if no_transfer_limit:

            max_transfers = None

        else:

            max_transfers = st.slider(
                "Maximum transfers",
                0,
                5,
                1,
            )

        max_walk = 0.0

        selected_modes = st.multiselect(
            "Preferred modes",
            [
                label
                for _, label in MODE_OPTIONS
            ],
            default=[
                label
                for _, label in MODE_OPTIONS
            ],
        )

        dep_time = st.text_input(
            "Departure time (HH:MM)",
            value="",
        )

        deadline = st.text_input(
            "Arrive by (HH:MM)",
            value="",
        )

        simulate = st.toggle(
            "Simulate live disruptions",
            value=False,
        )

        st.divider()

        st.caption(
            llm.label
        )

        # ----------------------------------------------------
        # CLEAR RESULT
        # ----------------------------------------------------

        if st.button(
            "🗑️ Clear result",
            use_container_width=True,
        ):

            st.session_state.output = None
            st.session_state.last_request = None

            st.rerun()

    # --------------------------------------------------------
    # INPUT SECTION
    # --------------------------------------------------------

    st.subheader(
        "Where are you going?"
    )

    text = st.text_area(
        "Describe your trip in natural language",
        value="",
        placeholder=EXAMPLE,
        height=100,
    )

    # Build stop name list for dropdowns
    try:
        from services import get_graph
        g = get_graph()
        stop_names = sorted(set(s.name for s in g.stops.values()))
    except Exception:
        stop_names = ["LB Nagar", "HITEC City", "Secunderabad", "Miyapur", "Kukatpally", "Gachibowli"]

    c1, c2 = st.columns(2)

    with c1:
        origin_sel = st.selectbox(
            "Origin (select from list)",
            options=[""] + stop_names,
            index=0,
            help="Select a stop or leave empty to use free text below",
        )
        origin = st.text_input(
            "Or type origin",
            value="",
            placeholder="e.g. LB Nagar",
        )
        if origin_sel and not origin.strip():
            origin = origin_sel

    with c2:
        dest_sel = st.selectbox(
            "Destination (select from list)",
            options=[""] + stop_names,
            index=0,
            help="Select a stop or leave empty to use free text below",
        )
        destination = st.text_input(
            "Or type destination",
            value="",
            placeholder="e.g. HITEC City",
        )
        if dest_sel and not destination.strip():
            destination = dest_sel

    # --------------------------------------------------------
    # PLAN BUTTON
    # --------------------------------------------------------

    plan = st.button(
        "🚀 Plan journey",
        type="primary",
        use_container_width=True,
    )

    # --------------------------------------------------------
    # FIRST PAGE
    # --------------------------------------------------------

    if (
        not plan
        and st.session_state.output is None
    ):

        st.caption(
            "Try the example: " + EXAMPLE
        )

        return

    # --------------------------------------------------------
    # ONLY RUN PIPELINE WHEN BUTTON IS CLICKED
    # --------------------------------------------------------

    if plan:

        # ----------------------------------------------------
        # VALIDATE INPUT
        # ----------------------------------------------------

        if (
            not origin.strip()
            and not destination.strip()
            and not text.strip()
        ):

            st.error(
                "Provide an origin and destination, "
                "or describe the trip in words."
            )

            return

        # ----------------------------------------------------
        # VALIDATE TIME
        # ----------------------------------------------------

        departure = parse_time_input(
            dep_time
        )

        arrival = parse_time_input(
            deadline
        )

        if (
            dep_time.strip()
            and departure is None
        ):

            st.error(
                "Departure time must be HH:MM (24-hour)."
            )

            return

        if (
            deadline.strip()
            and arrival is None
        ):

            st.error(
                "Deadline must be HH:MM (24-hour)."
            )

            return

        # ----------------------------------------------------
        # MODES
        # ----------------------------------------------------

        requested_modes = None

        if (
            selected_modes
            and len(selected_modes) < len(MODE_OPTIONS)
        ):

            requested_modes = [
                Mode(label.lower())
                for label in selected_modes
            ]

        # ----------------------------------------------------
        # BUILD REQUEST
        # ----------------------------------------------------

        request = JourneyRequest(

            origin=origin.strip() or "",

            destination=destination.strip() or "",

            text=text.strip() or None,

            departure_time=departure,

            arrival_deadline=arrival,

            budget=(
                budget
                if budget > 0
                else None
            ),

            max_transfers=max_transfers,

            max_walk_m=max_walk,

            modes=requested_modes,

            profile=profile,

            priorities=["balanced"],
        )

        # ----------------------------------------------------
        # RUN PIPELINE
        # ----------------------------------------------------

        try:

            with st.spinner(
                "Planning "
                "(Intent → RAG + live status → "
                "routing → evaluation)…"
            ):

                output = run_pipeline(
                    request,
                    simulate=simulate,
                )

            # ------------------------------------------------
            # IMPORTANT:
            # SAVE RESULT TO SESSION STATE
            # ------------------------------------------------

            st.session_state.output = output
            st.session_state.last_request = request

        # ----------------------------------------------------
        # ERROR HANDLING
        # ----------------------------------------------------

        except StopNotFoundError as exc:

            st.error(
                str(exc)
            )

            return

        except ValueError as exc:

            st.error(
                str(exc)
            )

            return

        except Exception as exc:

            st.error(
                f"Planning failed: {exc}"
            )

            with st.expander(
                "Traceback"
            ):

                st.code(
                    traceback.format_exc()
                )

            return

    # --------------------------------------------------------
    # RENDER STORED RESULT
    # --------------------------------------------------------

    if st.session_state.output is not None:

        st.divider()

        render(
            st.session_state.output
        )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()


### What was actually causing the problem

