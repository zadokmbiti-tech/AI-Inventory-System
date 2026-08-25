from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.models.models import Product, StockMovement, Sale, SaleItem, MovementType, User, TaxCategory
from app.schemas.schemas import StockMovementCreate, StockMovementOut, SaleCreate, SaleOut, VatSummary
from datetime import datetime, timedelta
from sqlalchemy import func
from app.services.auth import get_current_user

router = APIRouter(prefix="/api", tags=["Stock & Sales"])


# ─── Stock Movements ─────────────────────────────────────────────────────────

@router.post("/stock/movement", response_model=StockMovementOut, status_code=201)
def record_movement(payload: StockMovementCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    product = db.query(Product).filter(Product.id == payload.product_id, Product.user_id == user.id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if payload.movement_type in [MovementType.OUT, MovementType.LOSS]:
        if product.current_stock < payload.quantity:
            raise HTTPException(status_code=400, detail=f"Insufficient stock. Available: {product.current_stock}")
        product.current_stock -= payload.quantity
    else:
        product.current_stock += payload.quantity

    movement = StockMovement(
        product_id=product.id,
        movement_type=payload.movement_type,
        quantity=payload.quantity,
        balance_after=product.current_stock,
        notes=payload.notes,
    )
    db.add(movement)
    db.commit()
    db.refresh(movement)
    return movement


@router.get("/stock/movements/{product_id}", response_model=List[StockMovementOut])
def get_movements(product_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    product = db.query(Product).filter(Product.id == product_id, Product.user_id == user.id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return db.query(StockMovement).filter(StockMovement.product_id == product_id).order_by(StockMovement.created_at.desc()).limit(50).all()


# ─── Sales ────────────────────────────────────────────────────────────────────

@router.post("/sales", response_model=SaleOut, status_code=201)
def record_sale(payload: SaleCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    subtotal_total = 0.0
    tax_total = 0.0
    items_to_create = []

    for item in payload.items:
        product = db.query(Product).filter(Product.id == item.product_id, Product.user_id == user.id).first()
        if not product:
            raise HTTPException(status_code=404, detail=f"Product {item.product_id} not found")
        if product.current_stock < item.quantity:
            raise HTTPException(status_code=400, detail=f"Insufficient stock for {product.name}")

        subtotal = item.quantity * item.unit_price  # tax-exclusive
        # VAT only applies for STANDARD/REDUCED categories; ZERO_RATED and EXEMPT charge 0%
        if product.tax_category in (TaxCategory.STANDARD, TaxCategory.REDUCED):
            applied_rate = product.tax_rate
        else:
            applied_rate = 0.0
        tax_amount = round(subtotal * applied_rate / 100, 2)

        subtotal_total += subtotal
        tax_total += tax_amount
        items_to_create.append((product, item, subtotal, applied_rate, tax_amount))

    grand_total = round(subtotal_total + tax_total, 2)

    # All checks passed  commit everything
    sale = Sale(
        user_id=user.id,
        subtotal_amount=round(subtotal_total, 2),
        tax_amount=round(tax_total, 2),
        total_amount=grand_total,
        payment_method=payload.payment_method,
        notes=payload.notes,
    )
    db.add(sale)
    db.flush()

    for product, item, subtotal, applied_rate, tax_amount in items_to_create:
        product.current_stock -= item.quantity
        sale_item = SaleItem(
            sale_id=sale.id,
            product_id=item.product_id,
            quantity=item.quantity,
            unit_price=item.unit_price,
            subtotal=subtotal,
            tax_category=product.tax_category,
            tax_rate=applied_rate,
            tax_amount=tax_amount,
        )
        db.add(sale_item)
        movement = StockMovement(
            product_id=item.product_id,
            movement_type=MovementType.OUT,
            quantity=item.quantity,
            balance_after=product.current_stock,
            notes=f"Sale #{sale.id}",
        )
        db.add(movement)

    db.commit()
    db.refresh(sale)
    return sale


@router.get("/sales", response_model=List[SaleOut])
def list_sales(limit: int = 20, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(Sale).filter(Sale.user_id == user.id).order_by(Sale.created_at.desc()).limit(limit).all()


# ─── VAT / Tax Reporting ─────────────────────────────────────────────────────

@router.get("/sales/vat-summary", response_model=VatSummary)
def vat_summary(days: int = 30, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """
    Output VAT summary for KRA filing purposes: net sales, VAT collected,
    and a breakdown by tax category (STANDARD / REDUCED / ZERO_RATED / EXEMPT).
    This covers OUTPUT tax only (what you've charged customers)  it does not
    net off input VAT on your own purchases, which you'd still need for the
    actual iTax VAT return.
    """
    since = datetime.utcnow() - timedelta(days=days)

    rows = (
        db.query(
            SaleItem.tax_category,
            func.sum(SaleItem.subtotal).label("net"),
            func.sum(SaleItem.tax_amount).label("vat"),
            func.count(SaleItem.id).label("cnt"),
        )
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(Sale.user_id == user.id, Sale.created_at >= since)
        .group_by(SaleItem.tax_category)
        .all()
    )

    breakdown = [
        {
            "tax_category": r.tax_category.value,
            "net_sales": round(r.net or 0, 2),
            "vat_amount": round(r.vat or 0, 2),
            "item_count": r.cnt,
        }
        for r in rows
    ]

    net_sales = round(sum(r["net_sales"] for r in breakdown), 2)
    output_vat = round(sum(r["vat_amount"] for r in breakdown), 2)

    return VatSummary(
        period_days=days,
        net_sales=net_sales,
        output_vat_collected=output_vat,
        gross_sales=round(net_sales + output_vat, 2),
        by_tax_category=breakdown,
        disclaimer=(
            "Figures reflect output VAT only, based on rates set per product. "
            "Confirm product tax categorisation and current rates against the "
            "VAT Act 2013 / latest KRA guidance before filing  this is not tax advice."
        ),
    )
