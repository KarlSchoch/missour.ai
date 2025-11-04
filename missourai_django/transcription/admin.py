from django.contrib import admin

# Register your models here.
from .models import Transcript, Topic

admin.site.register([Transcript, Topic])