"""Build Gold GPU outputs."""


def build_current_prices(conn):
    """
    Materializes the current GPU prices view.
    """
    ...


def build_price_stats(conn):
    """
    Builds historical aggregates (min, avg, etc.).
    """
    ...


def build_all(conn):
    build_current_prices(conn)
    build_price_stats(conn)
