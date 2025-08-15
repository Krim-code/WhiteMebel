from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

class LimitPageNumberPagination(PageNumberPagination):
    page_size = 24
    page_size_query_param = "limit"
    max_page_size = 200

    def get_paginated_response(self, data, extra: dict | None = None):
        extra = extra or {}
        return Response({
            "count": self.page.paginator.count,
            "next": self.get_next_link(),
            "previous": self.get_previous_link(),
            "results": data,
            **extra,  # сюда уедут filters и т.п.
        })