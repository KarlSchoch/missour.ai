from django.urls import path
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.routers import DefaultRouter
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils.decorators import method_decorator
from django.urls import include
from itertools import count
from .models import Topic
from .api_views import TopicViewSet, SummaryViewSet

_ITEMS = []
_id_counter = count()

class Ping(APIView):

    def get(self, request):
        return Response({"ok": True, "user": request.user.get_username()})

app_name = 'api'

@method_decorator(ensure_csrf_cookie, name="dispatch")
class Items(APIView):

    def get(self, request):
        return Response(_ITEMS)
    
    def post(self, request):
        name = request.data.get("name", "Untitled")
        item = {"id": next(_id_counter), "name": name}
        _ITEMS.append(item)
        return Response(item, status=201)

# @method_decorator(ensure_csrf_cookie, name="dispatch")
# class Topics(APIView):

#     def get(self, request):
#         print("hello")
#         return Response(list(Topic.objects.values("id", "topic", "description")))

router = DefaultRouter()
router.register(r"topics", TopicViewSet)
router.register(r"summaries", SummaryViewSet)

urlpatterns = [
    path("", include(router.urls))
    # path("ping/", Ping.as_view(), name="ping"),
    # path("items/", Items.as_view(), name="items"),
    # path("topics/", Topics.as_view(), name="topics"),
]