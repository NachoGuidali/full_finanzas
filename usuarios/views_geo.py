from django.http import JsonResponse, Http404
from django.contrib.auth.decorators import login_required
from .models import Pais, Provincia, Localidad

@login_required
def geo_paises(request):
    qs = Pais.objects.all().values("id","nombre","iso2").order_by("nombre")
    return JsonResponse({"paises": list(qs)})

@login_required
def geo_provincias(request):
    pais_id = request.GET.get("pais_id")
    iso2    = request.GET.get("iso2")
    if not pais_id and not iso2:
        raise Http404("Falta pais_id o iso2")
    if iso2:
        qs = Provincia.objects.filter(pais__iso2=iso2).values("id","nombre").order_by("nombre")
    else:
        qs = Provincia.objects.filter(pais_id=pais_id).values("id","nombre").order_by("nombre")
    return JsonResponse({"provincias": list(qs)})

@login_required
def geo_localidades(request):
    prov_id = request.GET.get("provincia_id")
    if not prov_id:
        raise Http404("Falta provincia_id")
    qs = Localidad.objects.filter(provincia_id=prov_id).values("id","nombre").order_by("nombre")
    return JsonResponse({"localidades": list(qs)})