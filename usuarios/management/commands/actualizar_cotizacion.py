import requests
from decimal import Decimal, ROUND_HALF_UP
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils.timezone import now
from usuarios.models import Cotizacion

Q2 = lambda x: Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
Q6 = lambda x: Decimal(x).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

def apply_bps(base: Decimal, bps: int, side: str) -> Decimal:
    """
    side: 'compra' => (1 - bps/10000)
          'venta'  => (1 + bps/10000)
    """
    factor = Decimal("1") + (Decimal(bps) / Decimal("10000"))
    if side == "compra":
        return Q2(Decimal(base) / factor)  # alternativa: base*(1 - bps/10000)
    return Q2(Decimal(base) * factor)

class Command(BaseCommand):
    help = 'Actualiza la cotización de USDT (Binance) y USD (DolarAPI) guardando refs y finales.'

    def handle(self, *args, **kwargs):
        self.actualizar_usdt()
        self.actualizar_usd()

    def actualizar_usdt(self):
        url = 'https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search'
        data = {
            "asset": "USDT",
            "fiat": "ARS",
            "tradeType": "SELL",   # vendedores de USDT → precio de venta de USDT (lado “ask”)
            "payTypes": [],
            "page": 1,
            "rows": 5
        }
        headers = {'Content-Type': 'application/json'}

        spread_bps = getattr(settings, 'SPREAD_BPS_USDT', 200)

        try:
            r = requests.post(url, json=data, headers=headers, timeout=12)
            r.raise_for_status()
            payload = r.json()
            results = payload.get('data', []) or []
            precios = []
            for ad in results:
                adv = ad.get('adv', {})
                p = adv.get('price')
                if p:
                    precios.append(Q6(p))

            if not precios:
                self.stdout.write(self.style.WARNING("USDT: sin precios P2P (Binance)."))
                return

            ref = sum(precios) / Decimal(len(precios))  # referencia “cruda”
            ref = Q6(ref)

            # Publicar finales con margen (simétrico):
            compra = apply_bps(ref, spread_bps, side="compra")
            venta  = apply_bps(ref, spread_bps, side="venta")

            Cotizacion.objects.create(
                moneda='USDT',
                compra=compra,   # con margen
                venta=venta,     # con margen
                ref_compra=ref,  # crudo
                ref_venta=ref,   # crudo (mismo valor)
                fecha=now(),
                
                margin_bps=spread_bps
            )

            self.stdout.write(self.style.SUCCESS(
                f"[USDT] ref≈{ref} | compra={compra} venta={venta} (bps={spread_bps})"
            ))

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"[ERROR USDT Binance] {e}"))

    def actualizar_usd(self):
        spread_bps = getattr(settings, 'SPREAD_BPS_USD', 200)
        try:
            url = "https://dolarapi.com/v1/dolares"
            r = requests.get(url, timeout=12)
            r.raise_for_status()
            data = r.json() or []

            oficial = next((x for x in data if x.get('casa') == 'oficial'), None)
            if not oficial:
                self.stdout.write(self.style.WARNING("USD: no se encontró 'oficial' en dolarapi."))
                return

            ref_compra = Q6(oficial['compra'])
            ref_venta  = Q6(oficial['venta'])

            # aplico margen simétrico
            compra = apply_bps(ref_compra, spread_bps, side="compra")
            venta  = apply_bps(ref_venta,  spread_bps, side="venta")

            Cotizacion.objects.create(
                moneda='USD',
                compra=compra,
                venta=venta,
                ref_compra=ref_compra,
                ref_venta=ref_venta,
                fecha=now(),
                
                margin_bps=spread_bps
            )

            self.stdout.write(self.style.SUCCESS(
                f"[USD] ref_compra={ref_compra} ref_venta={ref_venta} | compra={compra} venta={venta} (bps={spread_bps})"
            ))

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"[ERROR USD DolarAPI] {e}"))
