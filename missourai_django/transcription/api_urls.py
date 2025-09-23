from django.urls import path
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils.decorators import method_decorator
from itertools import count

_ITEMS = []
_id_counter = count()

class Ping(APIView):

    def get(self, request):
        return Response({"ok": True, "user": request.user.get_username()})

@method_decorator(ensure_csrf_cookie, name="dispatch")
class Items(APIView):

    def get(self, request):
        return Response(_ITEMS)
    
    def post(self, request):
        name = request.data.get("name", "Untitled")
        item = {"id": next(_id_counter), "name": name}
        _ITEMS.append(item)
        return Response(item, status=201)

urlpatterns = [
    path("ping/", Ping.as_view(), name="api-ping"),
    path("items/", Items.as_view(), name="api-items"),
]