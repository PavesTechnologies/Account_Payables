from fastapi import APIRouter


router = APIRouter()


@router.get("/health")
def health_check():
    return {"status": "Accounts Payable Module API is healthy"}


@router.get("/items")
def list_items():
    # Sample endpoint to list items
    return {"items": ["item1", "item2", "item3"]}
