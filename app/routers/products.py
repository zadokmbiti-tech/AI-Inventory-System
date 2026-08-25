from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database import get_db
from app.models.models import Product, Category, User
from app.schemas.schemas import ProductCreate, ProductUpdate, ProductOut, CategoryCreate, CategoryOut
from app.services.auth import get_current_user

router = APIRouter(prefix="/api", tags=["Products"])


# ─── Categories ──────────────────────────────────────────────────────────────

@router.post("/categories", response_model=CategoryOut, status_code=201)
def create_category(payload: CategoryCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    cat = Category(name=payload.name, user_id=user.id)
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


@router.get("/categories", response_model=List[CategoryOut])
def list_categories(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(Category).filter(Category.user_id == user.id).all()


# ─── Products ─────────────────────────────────────────────────────────────────

def _find_duplicate_product(
    db: Session, user_id: int, name: str, sku: Optional[str], exclude_id: Optional[int] = None
) -> Optional[Product]:
    """
    Look for an existing active product for this user with the same name
    (case-insensitive, trimmed) or the same SKU, so the same item can't be
    added twice. exclude_id lets update_product ignore the row being edited.
    """
    q = db.query(Product).filter(
        Product.user_id == user_id,
        Product.is_active == True,  # noqa: E712
    )
    if exclude_id is not None:
        q = q.filter(Product.id != exclude_id)

    name_clean = name.strip().lower()
    sku_clean = sku.strip().lower() if sku else None

    for existing in q.all():
        if existing.name.strip().lower() == name_clean:
            return existing
        if sku_clean and existing.sku and existing.sku.strip().lower() == sku_clean:
            return existing
    return None


@router.post("/products", response_model=ProductOut, status_code=201)
def create_product(payload: ProductCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    duplicate = _find_duplicate_product(db, user.id, payload.name, payload.sku)
    if duplicate:
        raise HTTPException(
            status_code=409,
            detail=f"A product named '{duplicate.name}' already exists.",
        )
    product = Product(**payload.model_dump(), user_id=user.id)
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.get("/products", response_model=List[ProductOut])
def list_products(
    category_id: Optional[int] = None,
    low_stock_only: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    q = db.query(Product).filter(Product.user_id == user.id, Product.is_active == True)
    if category_id:
        q = q.filter(Product.category_id == category_id)
    if low_stock_only:
        q = q.filter(Product.current_stock <= Product.reorder_point)
    return q.order_by(Product.name).all()


@router.get("/products/{product_id}", response_model=ProductOut)
def get_product(product_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    product = db.query(Product).filter(Product.id == product_id, Product.user_id == user.id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.patch("/products/{product_id}", response_model=ProductOut)
def update_product(product_id: int, payload: ProductUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    product = db.query(Product).filter(Product.id == product_id, Product.user_id == user.id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    updates = payload.model_dump(exclude_unset=True)
    new_name = updates.get("name", product.name)
    new_sku = updates.get("sku", product.sku)
    duplicate = _find_duplicate_product(db, user.id, new_name, new_sku, exclude_id=product.id)
    if duplicate:
        raise HTTPException(
            status_code=409,
            detail=f"A product named '{duplicate.name}' already exists.",
        )

    for field, value in updates.items():
        setattr(product, field, value)
    db.commit()
    db.refresh(product)
    return product


@router.delete("/products/{product_id}", status_code=204)
def delete_product(product_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    product = db.query(Product).filter(Product.id == product_id, Product.user_id == user.id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    product.is_active = False   # soft delete
    db.commit()