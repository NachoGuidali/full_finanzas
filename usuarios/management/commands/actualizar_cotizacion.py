import json
import requests
from decimal import Decimal, ROUND_HALF_UP
from django.core.management.base import BaseCommand
from django.utils.timezone import now
from usuarios.models import Cotizacion, ExchangeConfig

Q2 = lambda x: Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
Q6 = lambda x: Decimal(x).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def aplicar_spread(precio_ref: Decimal, bps: int, sentido: str) -> Decimal:
    """
    sentido:
      - 'compra' => precio que paga la casa al cliente (menor que ref)
      - 'venta'  => precio que cobra la casa al cliente (mayor que ref)
    """
    precio_ref = Decimal(precio_ref)
    factor = Decimal(bps) / Decimal("10000")
    if sentido == "compra":
        return Q2(precio_ref * (Decimal("1") - factor))
    return Q2(precio_ref * (Decimal("1") + factor))


class Command(BaseCommand):
    help = "Actualiza la cotización de USDT (Binance P2P) y USD (DolarAPI) aplicando spreads de ExchangeConfig"

    # --- Helper Binance: referencia promedio top N por tradeType ---
    def _binance_p2p_ref(self, trade_type: str, rows: int = 10) -> Decimal:
        url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
        payload = {
            "asset": "USDT",
            "fiat": "ARS",
            "tradeType": trade_type,  # "SELL" o "BUY"
            "page": 1,
            "rows": rows,
            "payTypes": [],
        }
        headers = {"Content-Type": "application/json", "Accept": "application/json"}

        r = requests.post(url, data=json.dumps(payload), headers=headers, timeout=12)
        r.raise_for_status()
        data = r.json().get("data", []) or []

        precios = []
        for item in data:
            adv = item.get("adv") or {}
            p = adv.get("price")
            if p:
                precios.append(Decimal(str(p)))

        if not precios:
            raise ValueError(f"No se encontraron precios Binance P2P tradeType={trade_type}")

        return Q6(sum(precios) / len(precios))

    def handle(self, *args, **kwargs):
        cfg = ExchangeConfig.current()

        self.actualizar_usdt(
            spread_bps_compra=cfg.spread_bps_usdt_compra,
            spread_bps_venta=cfg.spread_bps_usdt_venta,
        )
        self.actualizar_usd(
            spread_bps_compra=cfg.spread_bps_usd_compra,
            spread_bps_venta=cfg.spread_bps_usd_venta,
        )

    # ---------- USDT (Binance P2P) ----------
    def actualizar_usdt(self, spread_bps_compra: int, spread_bps_venta: int):
        try:
            # SELL: gente vende USDT -> precio al que tu cliente COMPRA (tu VENTA)
            ref_venta = self._binance_p2p_ref("BUY")
            # BUY: gente compra USDT -> precio al que tu cliente VENDE (tu COMPRA)
            ref_compra = self._binance_p2p_ref("SELL")

            compra = aplicar_spread(ref_compra, spread_bps_compra, "compra")
            venta = aplicar_spread(ref_venta, spread_bps_venta, "venta")

            Cotizacion.objects.create(
                moneda="USDT",
                compra=compra,
                venta=venta,
                fecha=now(),
                ref_compra=ref_compra,
                ref_venta=ref_venta,
                margin_bps_compra=spread_bps_compra,
                margin_bps_venta=spread_bps_venta,
                margin_bps=(spread_bps_compra + spread_bps_venta) // 2,
            )

            self.stdout.write(
                self.style.SUCCESS(
                    f"[USDT] ref_compra(BUY)={ref_compra} • ref_venta(SELL)={ref_venta} • "
                    f"compra={compra} (bps={spread_bps_compra}) • venta={venta} (bps={spread_bps_venta})"
                )
            )

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"[ERROR USDT Binance] {e}"))

    # ---------- USD (DolarAPI) ----------
    def actualizar_usd(self, spread_bps_compra: int, spread_bps_venta: int):
        url = "https://dolarapi.com/v1/dolares"
        try:
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            data = r.json()

            oficial = next((d for d in data if d.get("casa") == "blue"), None)
            if not oficial:
                self.stdout.write(self.style.WARNING("No se encontró la cotización 'Blue' en dolarapi.com"))
                return

            compra_raw = Decimal(str(oficial["compra"]))
            venta_raw = Decimal(str(oficial["venta"]))

            # refs separadas (SIN promedio)
            ref_compra = Q6(compra_raw)
            ref_venta = Q6(venta_raw)

            compra = aplicar_spread(ref_compra, spread_bps_compra, "compra")
            venta = aplicar_spread(ref_venta, spread_bps_venta, "venta")

            Cotizacion.objects.create(
                moneda="USD",
                compra=compra,
                venta=venta,
                fecha=now(),
                ref_compra=ref_compra,
                ref_venta=ref_venta,
                margin_bps_compra=spread_bps_compra,
                margin_bps_venta=spread_bps_venta,
                margin_bps=(spread_bps_compra + spread_bps_venta) // 2,
            )

            self.stdout.write(
                self.style.SUCCESS(
                    f"[USD] ref_compra={ref_compra} • ref_venta={ref_venta} • "
                    f"compra={compra} (bps={spread_bps_compra}) • venta={venta} (bps={spread_bps_venta})"
                )
            )

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"[ERROR USD DolarAPI] {e}"))