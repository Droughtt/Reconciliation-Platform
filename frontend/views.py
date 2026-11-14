from django.shortcuts import render
from django.http import JsonResponse

def index(request):
    return render(request, "frontend/index.html")

def ping(request):
    """Simple health check used for keep‑warm pings."""
    return JsonResponse({"status": "ok"})