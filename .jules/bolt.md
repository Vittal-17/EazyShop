## 2024-05-19 - Prevent N+1 Query in OrderItem View
**Learning:** Found N+1 query vulnerability in OrderItemViewSet when retrieving nested order/product fields in serializers.
**Action:** Always verify nested fields inside standard viewsets have appropriate prefetch/select queries attached to base queryset.
