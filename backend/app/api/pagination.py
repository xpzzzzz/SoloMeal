from fastapi import Query


class Page:
    """Bound SQL reads while keeping the existing array response contract."""

    def __init__(self, limit: int = Query(100, ge=1, le=200),
                 offset: int = Query(0, ge=0, le=100000)):
        self.limit = limit
        self.offset = offset
