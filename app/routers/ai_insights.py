from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import User, Product
from app.services.auth import get_current_user
from app.ml.intelligence import (
    get_low_stock_alerts,
    get_reorder_suggestions,
    forecast_demand,
    get_analytics_summary,
    get_product_performance_insights,
)

router = APIRouter(prefix="/api/ai", tags=["AI Insights"])


@router.get("/alerts")
def low_stock_alerts(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Get all products at or below reorder point with urgency levels."""
    return get_low_stock_alerts(user.id, db)


@router.get("/reorder/{product_id}")
def reorder_suggestion(product_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """AI-suggested reorder point and quantity for a specific product."""
    result = get_reorder_suggestions(product_id, user.id, db)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.post("/reorder/{product_id}/apply")
def apply_reorder_suggestion(product_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Apply AI reorder suggestion directly to the product."""
    suggestion = get_reorder_suggestions(product_id, user.id, db)
    if "error" in suggestion:
        raise HTTPException(status_code=404, detail=suggestion["error"])

    product = db.query(Product).filter(Product.id == product_id, Product.user_id == user.id).first()
    product.reorder_point = suggestion["suggested_reorder_point"]
    product.reorder_quantity = suggestion["suggested_reorder_quantity"]
    db.commit()
    return {"message": "Reorder settings updated", "applied": suggestion}


@router.get("/forecast/{product_id}")
def demand_forecast(
    product_id: int,
    days_ahead: int = Query(default=30, ge=7, le=90),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """30-day demand forecast using Prophet or moving average fallback."""
    result = forecast_demand(product_id, user.id, db, days_ahead)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/product-performance")
def product_performance(
    days: int = Query(default=30, ge=1, le=366),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Ranks all products by sales performance (units, revenue, trend) and
    returns best sellers, slow movers, and a suggestion for each.
    """
    return get_product_performance_insights(user.id, db, days)


@router.get("/analytics")
def analytics(
    days: int = Query(default=30, ge=7, le=365),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Sales analytics summary: revenue, profit, top products, daily chart."""
    return get_analytics_summary(user.id, db, days)
