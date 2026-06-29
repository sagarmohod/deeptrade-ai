"""Zerodha cost model — NSE charges as of 2025-2026.

Reference: https://zerodha.com/charges/
Updated: STT on options sell premium = 0.1% (was 0.0625%)
"""
from __future__ import annotations

from decimal import Decimal

from core.brokers.base import CostBreakdown


class ZerodhaCostModel:
    """Zerodha NSE cost model."""

    name = "zerodha"
    display_name = "Zerodha Kite"

    # Constants
    GST_RATE = Decimal("0.18")
    SEBI_FEE_RATE = Decimal("0.000001")  # ₹10 per crore
    STAMP_DUTY_BUY = Decimal("0.00003")

    def equity_intraday(self, side: str, qty: int, price: Decimal) -> CostBreakdown:
        """Equity intraday (MIS)."""
        turnover = Decimal(qty) * price
        brokerage = min(Decimal("20"), turnover * Decimal("0.0003"))
        stt = turnover * Decimal("0.00025") if side == "SELL" else Decimal("0")
        exchange_txn = turnover * Decimal("0.0000345")
        sebi_fee = turnover * self.SEBI_FEE_RATE
        stamp_duty = turnover * self.STAMP_DUTY_BUY if side == "BUY" else Decimal("0")
        gst = self.GST_RATE * (brokerage + exchange_txn + sebi_fee)

        return CostBreakdown(
            brokerage=brokerage,
            stt=stt,
            exchange_txn=exchange_txn,
            sebi_fee=sebi_fee,
            gst=gst,
            stamp_duty=stamp_duty,
        )

    def equity_delivery(self, side: str, qty: int, price: Decimal) -> CostBreakdown:
        """Equity delivery (CNC) — ₹0 brokerage on Zerodha."""
        turnover = Decimal(qty) * price
        brokerage = Decimal("0")
        stt = turnover * Decimal("0.001")  # 0.1% on both sides for delivery
        exchange_txn = turnover * Decimal("0.0000345")
        sebi_fee = turnover * self.SEBI_FEE_RATE
        stamp_duty = turnover * Decimal("0.00015") if side == "BUY" else Decimal("0")
        gst = self.GST_RATE * (brokerage + exchange_txn + sebi_fee)

        return CostBreakdown(
            brokerage=brokerage,
            stt=stt,
            exchange_txn=exchange_txn,
            sebi_fee=sebi_fee,
            gst=gst,
            stamp_duty=stamp_duty,
        )

    def equity_futures(self, side: str, qty: int, price: Decimal) -> CostBreakdown:
        """Equity futures (NRML/MIS)."""
        turnover = Decimal(qty) * price
        brokerage = min(Decimal("20"), turnover * Decimal("0.0003"))
        stt = turnover * Decimal("0.0002") if side == "SELL" else Decimal("0")  # 0.02% sell side
        exchange_txn = turnover * Decimal("0.0000173")  # NSE futures
        sebi_fee = turnover * self.SEBI_FEE_RATE
        stamp_duty = turnover * Decimal("0.00002") if side == "BUY" else Decimal("0")
        ipft = turnover * Decimal("0.0000005")  # Investor Protection Fund
        gst = self.GST_RATE * (brokerage + exchange_txn + sebi_fee + ipft)

        return CostBreakdown(
            brokerage=brokerage,
            stt=stt,
            exchange_txn=exchange_txn,
            sebi_fee=sebi_fee,
            gst=gst,
            stamp_duty=stamp_duty,
            ipft=ipft,
        )

    def equity_options(self, side: str, qty: int, premium: Decimal) -> CostBreakdown:
        """Equity options — most relevant for our scalping."""
        notional = Decimal(qty) * premium
        brokerage = Decimal("20")  # flat
        stt = notional * Decimal("0.001") if side == "SELL" else Decimal("0")  # 0.1% on sell premium
        exchange_txn = notional * Decimal("0.0003503")  # NSE options
        sebi_fee = notional * self.SEBI_FEE_RATE
        stamp_duty = notional * Decimal("0.00003") if side == "BUY" else Decimal("0")
        gst = self.GST_RATE * (brokerage + exchange_txn + sebi_fee)

        return CostBreakdown(
            brokerage=brokerage,
            stt=stt,
            exchange_txn=exchange_txn,
            sebi_fee=sebi_fee,
            gst=gst,
            stamp_duty=stamp_duty,
        )
