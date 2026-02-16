from django.contrib import admin

# Register your models here.
from .models import Transcript, Topic, Chunk, Tag, Summary

admin.site.register([Transcript, Topic, Chunk, Tag, Summary])