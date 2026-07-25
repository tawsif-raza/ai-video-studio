"""
Tiny formatting helper shared by command_builder and filter_graph_builder, so
numeric durations/times are embedded consistently in ffmpeg arguments and
filter-graph expressions.
"""


def format_seconds(value: float) -> str:
    """Trims trailing zeros so 2.0 -> '2', 2.5 -> '2.5' - ffmpeg accepts both,
    but the compact form keeps commands and filter graphs readable in
    --dry-run output."""
    return f"{value:g}"
