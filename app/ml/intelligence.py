import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.models import Product, SaleItem, Sale, StockMovement, MovementType


def get_low_stock_alerts(user_id: int, db: Session) -> List[dict]:
    """
    Returns products at or below reorder point with urgency level
    and estimated days until stockout based on recent sales velocity.
    """
    products = db.query(Product).filter(
        Product.user_id == user_id,
        Product.is_active == True
    ).all()

    alerts = []
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)

    for p in products:
        # Calculate average daily sales over last 30 days
        sold_last_30 = db.query(func.sum(SaleItem.quantity)).join(Sale).filter(
            SaleItem.product_id == p.id,
            Sale.created_at >= thirty_days_ago
        ).scalar() or 0

        daily_velocity = sold_last_30 / 30

        days_until_stockout = None
        if daily_velocity > 0:
            days_until_stockout = round(p.current_stock / daily_velocity, 1)

        # Determine urgency
        if p.reorder_point > 0 and p.current_stock <= p.reorder_point:
            if p.current_stock == 0:
                urgency = "out_of_stock"
            elif days_until_stockout is not None and days_until_stockout <= 3:
                urgency = "critical"
            elif days_until_stockout is not None and days_until_stockout <= 7:
                urgency = "warning"
            else:
                urgency = "low"

            alerts.append({
                "product_id": p.id,
                "product_name": p.name,
                "sku": p.sku,
                "current_stock": p.current_stock,
                "reorder_point": p.reorder_point,
                "reorder_quantity": p.reorder_quantity,
                "unit": p.unit,
                "days_until_stockout": days_until_stockout,
                "daily_velocity": round(daily_velocity, 2),
                "urgency": urgency,
            })

    # Sort: out_of_stock → critical → warning → low
    order = {"out_of_stock": 0, "critical": 1, "warning": 2, "low": 3}
    alerts.sort(key=lambda x: order.get(x["urgency"], 9))
    return alerts


def get_reorder_suggestions(product_id: int, user_id: int, db: Session) -> dict:
    """
    Suggests reorder point and reorder quantity based on:
    - Historical sales velocity (last 90 days)
    - Lead time assumption (default 3 days for SME context)
    - Safety stock = 1.5x average lead time demand
    """
    product = db.query(Product).filter(
        Product.id == product_id,
        Product.user_id == user_id
    ).first()

    if not product:
        return {"error": "Product not found"}

    ninety_days_ago = datetime.utcnow() - timedelta(days=90)
    sold = db.query(func.sum(SaleItem.quantity)).join(Sale).filter(
        SaleItem.product_id == product_id,
        Sale.created_at >= ninety_days_ago
    ).scalar() or 0

    daily_avg = sold / 90
    lead_time_days = 3  # configurable per business

    reorder_point = round((daily_avg * lead_time_days) + (1.5 * daily_avg * lead_time_days), 1)
    # Reorder qty = 2 weeks of supply
    reorder_quantity = round(daily_avg * 14, 1)

    return {
        "product_id": product.id,
        "product_name": product.name,
        "daily_avg_sales": round(daily_avg, 2),
        "lead_time_days": lead_time_days,
        "suggested_reorder_point": max(reorder_point, 1),
        "suggested_reorder_quantity": max(reorder_quantity, 1),
        "current_reorder_point": product.reorder_point,
        "current_reorder_quantity": product.reorder_quantity,
    }


def forecast_demand(product_id: int, user_id: int, db: Session, days_ahead: int = 30) -> dict:
    """
    Demand forecasting using Prophet if enough data exists (>30 data points),
    falls back to linear trend + noise model for new products.
    """
    product = db.query(Product).filter(
        Product.id == product_id,
        Product.user_id == user_id
    ).first()

    if not product:
        return {"error": "Product not found"}

    # Pull daily sales aggregated
    rows = (
        db.query(
            func.date(Sale.created_at).label("ds"),
            func.sum(SaleItem.quantity).label("y")
        )
        .join(SaleItem, Sale.id == SaleItem.sale_id)
        .filter(SaleItem.product_id == product_id)
        .group_by(func.date(Sale.created_at))
        .order_by(func.date(Sale.created_at))
        .all()
    )

    forecast_points = []
    suggested_reorder_point = product.reorder_point
    suggested_reorder_quantity = product.reorder_quantity

    if len(rows) >= 10:
        # Enough data — use Prophet
        try:
            from prophet import Prophet
            df = pd.DataFrame(rows, columns=["ds", "y"])
            df["ds"] = pd.to_datetime(df["ds"])
            df["y"] = df["y"].astype(float)

            model = Prophet(
                yearly_seasonality=False,
                weekly_seasonality=True,
                daily_seasonality=False,
                interval_width=0.80,
            )
            model.fit(df)

            future = model.make_future_dataframe(periods=days_ahead)
            forecast = model.predict(future)
            future_only = forecast.tail(days_ahead)

            for _, row in future_only.iterrows():
                forecast_points.append({
                    "date": row["ds"].strftime("%Y-%m-%d"),
                    "predicted_demand": max(0, round(row["yhat"], 2)),
                    "lower_bound": max(0, round(row["yhat_lower"], 2)),
                    "upper_bound": max(0, round(row["yhat_upper"], 2)),
                })

            avg_daily = future_only["yhat"].clip(lower=0).mean()
            suggested_reorder_point = round(avg_daily * 3 * 1.5, 1)
            suggested_reorder_quantity = round(avg_daily * 14, 1)

        except Exception as e:
            forecast_points = _simple_forecast(rows, days_ahead)

    else:
        # Not enough data — simple moving average forecast
        forecast_points = _simple_forecast(rows, days_ahead)

    return {
        "product_id": product.id,
        "product_name": product.name,
        "data_points_used": len(rows),
        "method": "prophet" if len(rows) >= 10 else "moving_average",
        "forecast": forecast_points,
        "suggested_reorder_point": max(suggested_reorder_point, 1),
        "suggested_reorder_quantity": max(suggested_reorder_quantity, 1),
    }


def _simple_forecast(rows: list, days_ahead: int) -> list:
    """Fallback: moving average with slight noise for new products."""
    if not rows:
        avg = 1.0
    else:
        values = [float(r[1]) for r in rows]
        avg = np.mean(values[-7:]) if len(values) >= 7 else np.mean(values)

    points = []
    today = datetime.utcnow().date()
    for i in range(1, days_ahead + 1):
        noise = np.random.normal(0, avg * 0.1)
        pred = max(0, round(avg + noise, 2))
        points.append({
            "date": (today + timedelta(days=i)).strftime("%Y-%m-%d"),
            "predicted_demand": pred,
            "lower_bound": max(0, round(pred * 0.7, 2)),
            "upper_bound": round(pred * 1.3, 2),
        })
    return points


def get_product_performance_insights(user_id: int, db: Session, days: int = 30) -> dict:
    """
    Ranks every active product by how well it's selling relative to the
    others, and attaches a plain-language suggestion for each — e.g. a
    best seller worth stocking more of, a slow mover worth discounting or
    dropping, or a product trending up/down versus the first half of the
    period.
    """
    since = datetime.utcnow() - timedelta(days=days)
    midpoint = datetime.utcnow() - timedelta(days=days / 2)

    products = db.query(Product).filter(
        Product.user_id == user_id,
        Product.is_active == True,
    ).all()

    rows = []
    for p in products:
        sale_items = (
            db.query(SaleItem)
            .join(Sale)
            .filter(SaleItem.product_id == p.id, Sale.created_at >= since)
            .all()
        )

        units_sold = sum(item.quantity for item in sale_items)
        revenue = sum(item.subtotal for item in sale_items)
        profit = sum(item.subtotal - (p.cost_price * item.quantity) for item in sale_items)

        first_half_units = sum(
            item.quantity for item in sale_items if item.sale.created_at < midpoint
        )
        second_half_units = units_sold - first_half_units

        if first_half_units > 0:
            trend_pct = round(((second_half_units - first_half_units) / first_half_units) * 100, 1)
        elif second_half_units > 0:
            trend_pct = 100.0  # went from nothing to something
        else:
            trend_pct = 0.0

        rows.append({
            "product_id": p.id,
            "product_name": p.name,
            "sku": p.sku,
            "units_sold": units_sold,
            "revenue": round(revenue, 2),
            "profit": round(profit, 2),
            "daily_velocity": round(units_sold / days, 2),
            "trend_pct": trend_pct,
            "current_stock": p.current_stock,
        })

    if not rows:
        return {"period_days": days, "products": [], "message": "No active products to analyze."}

    total_units = sum(r["units_sold"] for r in rows) or 1
    for r in rows:
        r["share_of_units_pct"] = round((r["units_sold"] / total_units) * 100, 1)

    rows.sort(key=lambda r: r["units_sold"], reverse=True)

    n = len(rows)
    for i, r in enumerate(rows):
        r["rank"] = i + 1
        if r["units_sold"] == 0:
            r["tier"] = "no_sales"
            r["suggestion"] = (
                f"No sales recorded in the last {days} days. Consider a discount, bundling it "
                "with a best seller, or discontinuing it if this continues."
            )
        elif i < max(1, round(n * 0.2)):
            r["tier"] = "best_seller"
            if r["trend_pct"] > 15:
                r["suggestion"] = (
                    f"Top performer and still climbing (+{r['trend_pct']}% vs the first half of "
                    "the period). Increase reorder quantity to avoid stockouts."
                )
            else:
                r["suggestion"] = (
                    "One of your best sellers. Make sure reorder point and quantity are high "
                    "enough that this never runs out."
                )
        elif i >= n - max(1, round(n * 0.2)):
            r["tier"] = "slow_mover"
            if r["trend_pct"] < -15:
                r["suggestion"] = (
                    f"Sales are slowing further ({r['trend_pct']}% vs the first half of the "
                    "period). Consider a promotion, bundling, or reducing how much you restock."
                )
            else:
                r["suggestion"] = (
                    "Consistently your weakest seller. Consider a discount to clear stock, or "
                    "phasing it out if margins are thin."
                )
        else:
            r["tier"] = "steady"
            if r["trend_pct"] > 20:
                r["suggestion"] = f"Trending up (+{r['trend_pct']}%) — worth watching for a reorder bump."
            elif r["trend_pct"] < -20:
                r["suggestion"] = f"Trending down ({r['trend_pct']}%) — keep an eye on it."
            else:
                r["suggestion"] = "Selling steadily — current stocking levels look about right."

    return {
        "period_days": days,
        "best_sellers": [r for r in rows if r["tier"] == "best_seller"],
        "slow_movers": [r for r in rows if r["tier"] in ("slow_mover", "no_sales")],
        "products": rows,
    }


def get_analytics_summary(user_id: int, db: Session, days: int = 30) -> dict:
    """Sales analytics: revenue, profit, top products, revenue by day."""
    since = datetime.utcnow() - timedelta(days=days)

    sales = db.query(Sale).filter(
        Sale.user_id == user_id,
        Sale.created_at >= since
    ).all()

    # Revenue is net of VAT — VAT collected isn't business income, it's owed to KRA.
    total_revenue = sum(s.subtotal_amount for s in sales)
    total_vat_collected = sum(s.tax_amount for s in sales)
    total_sales = len(sales)

    # Calculate cost from sale items
    total_cost = 0.0
    product_performance = {}

    for sale in sales:
        for item in sale.items:
            cost = item.product.cost_price * item.quantity
            total_cost += cost
            pid = item.product_id
            if pid not in product_performance:
                product_performance[pid] = {
                    "product_id": pid,
                    "product_name": item.product.name,
                    "units_sold": 0,
                    "revenue": 0.0,
                    "profit": 0.0,
                }
            product_performance[pid]["units_sold"] += item.quantity
            product_performance[pid]["revenue"] += item.subtotal
            product_performance[pid]["profit"] += item.subtotal - cost

    gross_profit = total_revenue - total_cost
    profit_margin = round((gross_profit / total_revenue * 100), 2) if total_revenue > 0 else 0

    top_products = sorted(
        product_performance.values(),
        key=lambda x: x["revenue"],
        reverse=True
    )[:5]

    # Revenue by day
    revenue_by_day = {}
    for sale in sales:
        day = sale.created_at.strftime("%Y-%m-%d")
        revenue_by_day[day] = revenue_by_day.get(day, 0) + sale.subtotal_amount

    revenue_chart = [{"date": k, "revenue": round(v, 2)} for k, v in sorted(revenue_by_day.items())]

    return {
        "period_days": days,
        "total_revenue": round(total_revenue, 2),
        "total_vat_collected": round(total_vat_collected, 2),
        "total_cost": round(total_cost, 2),
        "gross_profit": round(gross_profit, 2),
        "profit_margin": profit_margin,
        "total_sales": total_sales,
        "top_products": top_products,
        "revenue_by_day": revenue_chart,
    }
